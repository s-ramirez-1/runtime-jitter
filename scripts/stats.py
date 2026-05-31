# stats.py
import numpy as np
import sqlite3
import json
import sys
from pathlib import Path
from datetime import datetime
from itertools import combinations
from scipy import stats as scipy_stats

# ----------------------------
# CONFIG
# ----------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db_manager

# ----------------------------
# PAIRWISE EXPERIMENT PAIRS
# Generates every unique two-way combination of experiments
# so we test baseline vs stress_test, baseline vs cpu_pinned_0,
# and stress_test vs cpu_pinned_0 automatically.
# Adding a new experiment to the registry adds it here too
# with no code changes.
# ----------------------------
def get_experiment_pairs(experiments):
    names = [e["name"] for e in experiments]
    return list(combinations(names, 2))


# ----------------------------
# LOAD MEASUREMENTS FROM DB
# Pulls all time_seconds values for a given experiment
# directly from the measurements table so stats always
# reflect exactly what is in the database.
# ----------------------------
def load_measurements(experiment_name):
    con = db_manager.get_connection()
    cur = con.cursor()

    cur.execute("""
        SELECT m.time_seconds
        FROM measurements m
        JOIN runs r ON m.run_id = r.id
        WHERE r.experiment_name = ?
    """, (experiment_name,))

    rows = cur.fetchall()
    con.close()

    return np.array([r[0] for r in rows])


# ----------------------------
# COHEN'S D
# Effect size metric. Tells you how large the difference
# is between two groups, not just whether it is real.
#
# Interpretation:
#   |d| < 0.2  -> negligible
#   |d| < 0.5  -> small
#   |d| < 0.8  -> medium
#   |d| >= 0.8 -> large
# ----------------------------
def cohens_d(a, b):
    mean_diff = np.mean(a) - np.mean(b)
    pooled_std = np.sqrt((np.std(a, ddof=1) ** 2 + np.std(b, ddof=1) ** 2) / 2)

    if pooled_std == 0:
        return 0.0

    return mean_diff / pooled_std


# ----------------------------
# EFFECT SIZE LABEL
# Converts a Cohen's d value into a human-readable label
# for the summary report and dashboard display.
# ----------------------------
def effect_size_label(d):
    d = abs(d)
    if d < 0.2:
        return "negligible"
    elif d < 0.5:
        return "small"
    elif d < 0.8:
        return "medium"
    else:
        return "large"


# ----------------------------
# CONFIDENCE INTERVAL
# Bootstrap 95% confidence interval on the mean.
# We use bootstrap rather than the normal approximation
# because runtime distributions have long right tails
# and are rarely truly normal.
# ----------------------------
def bootstrap_ci(data, n_bootstrap=2000, ci=95):
    rng = np.random.default_rng(seed=42)
    means = [
        np.mean(rng.choice(data, size=len(data), replace=True))
        for _ in range(n_bootstrap)
    ]
    lower = np.percentile(means, (100 - ci) / 2)
    upper = np.percentile(means, 100 - (100 - ci) / 2)
    return lower, upper


# ----------------------------
# RUN PAIRWISE TESTS
# For each pair of experiments, runs:
#   - Welch's t-test (parametric, unequal variance)
#   - Mann-Whitney U test (non-parametric)
#   - Cohen's d effect size
#   - Bootstrap confidence intervals on both means
#
# Returns a list of result dicts, one per pair.
# ----------------------------
def run_pairwise_tests(experiments):
    pairs = get_experiment_pairs(experiments)
    results = []

    for exp_a, exp_b in pairs:
        data_a = load_measurements(exp_a)
        data_b = load_measurements(exp_b)

        if len(data_a) == 0 or len(data_b) == 0:
            print(f"[WARN] Skipping {exp_a} vs {exp_b} — insufficient data")
            continue

        # Welch's t-test
        t_stat, t_pval = scipy_stats.ttest_ind(data_a, data_b, equal_var=False)

        # Mann-Whitney U test
        u_stat, u_pval = scipy_stats.mannwhitneyu(
            data_a, data_b, alternative="two-sided"
        )

        # Cohen's d
        d = cohens_d(data_a, data_b)

        # Bootstrap CIs
        ci_a_low, ci_a_high = bootstrap_ci(data_a)
        ci_b_low, ci_b_high = bootstrap_ci(data_b)

        result = {
            "experiment_a":    exp_a,
            "experiment_b":    exp_b,
            "n_a":             len(data_a),
            "n_b":             len(data_b),
            "mean_a":          float(np.mean(data_a)),
            "mean_b":          float(np.mean(data_b)),
            "std_a":           float(np.std(data_a, ddof=1)),
            "std_b":           float(np.std(data_b, ddof=1)),
            "ci_a_low":        float(ci_a_low),
            "ci_a_high":       float(ci_a_high),
            "ci_b_low":        float(ci_b_low),
            "ci_b_high":       float(ci_b_high),
            "welch_t":         float(t_stat),
            "welch_p":         float(t_pval),
            "mannwhitney_u":   float(u_stat),
            "mannwhitney_p":   float(u_pval),
            "cohens_d":        float(d),
            "effect_size":     effect_size_label(d),
            # Significant at p < 0.05 on both tests for a conservative claim
            "significant":     int(t_pval < 0.05 and u_pval < 0.05),
            "created_at":      datetime.now().isoformat()
        }

        results.append(result)

        print(f"\n[STATS] {exp_a} vs {exp_b}")
        print(f"  n              : {len(data_a)} vs {len(data_b)}")
        print(f"  mean           : {np.mean(data_a):.6f} vs {np.mean(data_b):.6f}")
        print(f"  95% CI (a)     : [{ci_a_low:.6f}, {ci_a_high:.6f}]")
        print(f"  95% CI (b)     : [{ci_b_low:.6f}, {ci_b_high:.6f}]")
        print(f"  Welch t-test   : t={t_stat:.4f}  p={t_pval:.6f}")
        print(f"  Mann-Whitney U : U={u_stat:.1f}  p={u_pval:.6f}")
        print(f"  Cohen's d      : {d:.4f}  ({effect_size_label(d)})")
        print(f"  Significant    : {'YES' if result['significant'] else 'NO'}")

    return results


# ----------------------------
# SAVE RESULTS TO DB
# Inserts each pairwise result into the statistical_tests
# table. Clears previous results for the same pair first
# so re-running the pipeline always reflects current data.
# ----------------------------
def save_results(results):
    con = db_manager.get_connection()
    cur = con.cursor()

    for r in results:
        # Remove stale result for this pair before inserting
        cur.execute("""
            DELETE FROM statistical_tests
            WHERE experiment_a = ? AND experiment_b = ?
        """, (r["experiment_a"], r["experiment_b"]))

        cur.execute("""
            INSERT INTO statistical_tests (
                experiment_a, experiment_b,
                n_a, n_b,
                mean_a, mean_b,
                std_a, std_b,
                ci_a_low, ci_a_high,
                ci_b_low, ci_b_high,
                welch_t, welch_p,
                mannwhitney_u, mannwhitney_p,
                cohens_d, effect_size,
                significant, created_at
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
        """, (
            r["experiment_a"],    r["experiment_b"],
            r["n_a"],             r["n_b"],
            r["mean_a"],          r["mean_b"],
            r["std_a"],           r["std_b"],
            r["ci_a_low"],        r["ci_a_high"],
            r["ci_b_low"],        r["ci_b_high"],
            r["welch_t"],         r["welch_p"],
            r["mannwhitney_u"],   r["mannwhitney_p"],
            r["cohens_d"],        r["effect_size"],
            r["significant"],     r["created_at"]
        ))

    con.commit()
    con.close()
    print(f"\n[STATS] Saved {len(results)} pairwise results to database")


# ----------------------------
# EXPORT LATEX TABLE
# Writes a publication-ready LaTeX table of all pairwise
# results including means, CIs, p-values, and effect sizes.
# ----------------------------
def export_latex(results):
    out = PROJECT_ROOT / "paper_figures" / "stats_table.tex"
    out.parent.mkdir(parents=True, exist_ok=True)

    lines = []
    lines.append("\\begin{tabular}{llcccccc}")
    lines.append("\\hline")
    lines.append(
        "A & B & Mean A & Mean B & Welch p & MW p & Cohen's d & Effect \\\\"
    )
    lines.append("\\hline")

    for r in results:
        sig = "*" if r["significant"] else ""
        lines.append(
            f"{r['experiment_a']} & {r['experiment_b']} & "
            f"{r['mean_a']:.5f} & {r['mean_b']:.5f} & "
            f"{r['welch_p']:.4f}{sig} & {r['mannwhitney_p']:.4f}{sig} & "
            f"{r['cohens_d']:.3f} & {r['effect_size']} \\\\"
        )

    lines.append("\\hline")
    lines.append("\\multicolumn{8}{l}{* significant at p < 0.05 on both tests} \\\\")
    lines.append("\\end{tabular}")

    out.write_text("\n".join(lines))
    print(f"[STATS] LaTeX table saved to {out}")


# ----------------------------
# MAIN
# ----------------------------
def main():
    print("\n=== STATISTICAL HYPOTHESIS TESTING ===")

    db_manager.create_tables()
    db_manager.seed_default_experiments()

    experiments = db_manager.get_experiments()

    if not experiments:
        print("[ERROR] No experiments found in registry")
        return

    results = run_pairwise_tests(experiments)

    if not results:
        print("[ERROR] No results produced — check that measurements exist in the DB")
        return

    save_results(results)
    export_latex(results)

    print("\n=== DONE ===")


if __name__ == "__main__":
    main()