# anomaly.py
import numpy as np
import sys
from pathlib import Path
from datetime import datetime
from sklearn.ensemble import IsolationForest

# ----------------------------
# CONFIG
# ----------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db_manager

DEFAULT_CONTAMINATION = 0.1


# ----------------------------
# PARSE CONTAMINATION
# Accepts integers (e.g. 0, 1) and floats (e.g. 0.1, 0.05).
# Must be strictly between 0 and 1 exclusive, matching
# scikit-learn's requirement for the contamination parameter.
# Returns None on any invalid input.
# ----------------------------
def _parse_contamination(raw):
    try:
        value = float(raw)
        if 0 < value < 1:
            return value
        else:
            return None
    except (ValueError, TypeError):
        return None


# ----------------------------
# CONTAMINATION PROMPT
# Walks the user through selecting a contamination parameter
# before any ML work begins. Returns a valid float between
# 0 and 1, or None if the user declines and we should skip.
#
# Flow:
#   1. Explain what Isolation Forest is and ask for a value.
#   2. If valid float in (0, 1) — use it.
#   3. If invalid — offer the 0.1 default with y/n confirmation.
#   4. If they reject the default — one final chance to enter
#      a valid value. If still invalid — return None (skip ML).
# ----------------------------
def prompt_contamination():
    print("\n" + "=" * 60)
    print("  MACHINE LEARNING — ANOMALY DETECTION SETUP")
    print("=" * 60)
    print("""
We are going to use a machine learning model called Isolation
Forest to determine if a particular run of the baseline test
is behaving differently from other baseline runs.

To be able to achieve this the Isolation Forest model needs
a 'contamination parameter' that tells the model roughly what
fraction of your runs you expect to be anomalous.

Please enter a real number between 0 and 1.
  Example: 0.1  means roughly 1 in 10 runs flagged as anomalous.
  Example: 0.05 means roughly 1 in 20 runs flagged as anomalous.
""")

    raw = input("  Contamination parameter: ").strip()
    value = _parse_contamination(raw)

    # ----------------------------
    # VALID INPUT — USE IT
    # ----------------------------
    if value is not None:
        print(f"\n[ML] Using contamination parameter: {value}")
        return value

    # ----------------------------
    # INVALID INPUT — OFFER DEFAULT
    # ----------------------------
    print(f"""
No valid contamination parameter selected. This program will
use {DEFAULT_CONTAMINATION} so it might flag roughly 1 in 10
runs as anomalous.

Is this acceptable? (y/n)""")

    confirm = input("  > ").strip().lower()

    if confirm == "y":
        print(f"\n[ML] Using default contamination parameter: {DEFAULT_CONTAMINATION}")
        return DEFAULT_CONTAMINATION

    if confirm == "n":
        # ----------------------------
        # DEFAULT REJECTED — ONE FINAL CHANCE
        # ----------------------------
        print(f"""
You rejected the {DEFAULT_CONTAMINATION} contamination parameter.
Please enter a valid integer or double between 0 and 1 to
continue the program.""")

        raw2 = input("\n  Contamination parameter: ").strip()
        value2 = _parse_contamination(raw2)

        if value2 is not None:
            print(f"\n[ML] Using contamination parameter: {value2}")
            return value2

        # ----------------------------
        # STILL INVALID — SKIP ML
        # ----------------------------
        print("\n[ML] No valid parameter provided — skipping anomaly detection.")
        return None

    # ----------------------------
    # NEITHER y NOR n — SKIP ML
    # Treat unrecognised input as a signal to skip rather
    # than looping indefinitely on the y/n question.
    # ----------------------------
    print("\n[ML] Unrecognised input — skipping anomaly detection.")
    return None


# ----------------------------
# BUILD FEATURE VECTORS
# For each run of an experiment, computes a 7-dimensional
# feature vector from its measurements:
#   mean, std, min, max, p95, p99, IQR
#
# Each run becomes one row. The model trains on these rows
# so anomaly detection operates at the run level, not the
# individual measurement level.
# ----------------------------
def build_feature_vectors(experiment_name):
    con = db_manager.get_connection()
    cur = con.cursor()

    cur.execute("""
        SELECT id FROM runs
        WHERE experiment_name = ?
        ORDER BY timestamp ASC
    """, (experiment_name,))

    run_ids = [row[0] for row in cur.fetchall()]

    if not run_ids:
        con.close()
        return [], []

    feature_rows  = []
    valid_run_ids = []

    for run_id in run_ids:
        cur.execute("""
            SELECT time_seconds FROM measurements
            WHERE run_id = ?
        """, (run_id,))

        times = np.array([row[0] for row in cur.fetchall()])

        # Need at least 5 measurements to compute meaningful features.
        if len(times) < 5:
            continue

        iqr = float(np.percentile(times, 75) - np.percentile(times, 25))

        features = [
            float(np.mean(times)),
            float(np.std(times, ddof=1)),
            float(np.min(times)),
            float(np.max(times)),
            float(np.percentile(times, 95)),
            float(np.percentile(times, 99)),
            iqr
        ]

        feature_rows.append(features)
        valid_run_ids.append(run_id)

    con.close()
    return valid_run_ids, feature_rows


# ----------------------------
# RUN ISOLATION FOREST
# Trains one model per experiment so anomalies are always
# judged within the context of that experiment's own runs,
# not against a mixed population.
#
# Also computes a Z-score flag on the run mean as a secondary
# signal. A run flagged by BOTH methods is high-confidence.
# ----------------------------
def run_isolation_forest(experiment_name, contamination):
    run_ids, feature_rows = build_feature_vectors(experiment_name)

    if len(run_ids) < 3:
        print(f"[ML] {experiment_name}: fewer than 3 usable runs — skipping")
        return []

    X = np.array(feature_rows)

    # Train Isolation Forest on this experiment's runs only
    model = IsolationForest(
        contamination=contamination,
        random_state=42,
        n_estimators=100
    )
    model.fit(X)

    # Predictions: -1 = anomaly, 1 = normal
    predictions = model.predict(X)

    # Raw anomaly scores — more negative = more anomalous
    scores = model.decision_function(X)

    # Z-score on the mean feature (column 0) as secondary signal
    means         = X[:, 0]
    mean_of_means = np.mean(means)
    std_of_means  = np.std(means, ddof=1) if len(means) > 1 else 1.0
    z_scores      = (
        (means - mean_of_means) / std_of_means
        if std_of_means > 0
        else np.zeros(len(means))
    )

    results = []

    for i, run_id in enumerate(run_ids):
        is_anomaly_if  = predictions[i] == -1
        is_anomaly_z   = abs(z_scores[i]) > 3.0
        # High confidence when both methods agree
        high_confidence = is_anomaly_if and is_anomaly_z

        result = {
            "run_id":           run_id,
            "experiment_name":  experiment_name,
            "contamination":    contamination,
            "anomaly_score":    float(scores[i]),
            "z_score":          float(z_scores[i]),
            "is_anomaly":       int(is_anomaly_if),
            "z_score_flag":     int(is_anomaly_z),
            "high_confidence":  int(high_confidence),
            "features": {
                "mean": feature_rows[i][0],
                "std":  feature_rows[i][1],
                "min":  feature_rows[i][2],
                "max":  feature_rows[i][3],
                "p95":  feature_rows[i][4],
                "p99":  feature_rows[i][5],
                "iqr":  feature_rows[i][6]
            },
            "created_at": datetime.now().isoformat()
        }

        results.append(result)

    # Per-experiment summary
    n_flagged = sum(1 for r in results if r["is_anomaly"])
    n_hc      = sum(1 for r in results if r["high_confidence"])

    print(f"\n[ML] {experiment_name}")
    print(f"  Runs analysed  : {len(results)}")
    print(f"  Anomalies (IF) : {n_flagged}")
    print(f"  High confidence: {n_hc}")

    for r in results:
        if r["is_anomaly"]:
            hc = " *** HIGH CONFIDENCE" if r["high_confidence"] else ""
            print(f"  [ANOMALY] run_id={r['run_id']:<4} "
                  f"score={r['anomaly_score']:.4f}  "
                  f"z={r['z_score']:.2f}  "
                  f"mean={r['features']['mean']:.6f}{hc}")

    return results


# ----------------------------
# SAVE RESULTS TO DB
# Clears previous anomaly flags for each experiment before
# inserting so re-running always reflects the current model.
# ----------------------------
def save_results(results):
    if not results:
        return

    con = db_manager.get_connection()
    cur = con.cursor()

    # Clear previous results per experiment before inserting
    experiments_seen = set(r["experiment_name"] for r in results)

    for exp in experiments_seen:
        cur.execute("""
            DELETE FROM anomaly_flags
            WHERE experiment_name = ?
        """, (exp,))

    for r in results:
        cur.execute("""
            INSERT INTO anomaly_flags (
                run_id, experiment_name, contamination,
                anomaly_score, z_score,
                is_anomaly, z_score_flag, high_confidence,
                features_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            r["run_id"],
            r["experiment_name"],
            r["contamination"],
            r["anomaly_score"],
            r["z_score"],
            r["is_anomaly"],
            r["z_score_flag"],
            r["high_confidence"],
            str(r["features"]),
            r["created_at"]
        ))

    con.commit()
    con.close()
    print(f"\n[ML] Saved {len(results)} anomaly records to database")


# ----------------------------
# MAIN
# ----------------------------
def main():
    print("\n=== ANOMALY DETECTION ===")

    # ----------------------------
    # CONTAMINATION PROMPT
    # Must happen before any model work. If the user declines
    # or provides no valid input we exit cleanly without
    # touching the database or running any models.
    # ----------------------------
    contamination = prompt_contamination()

    if contamination is None:
        print("[ML] Anomaly detection skipped.")
        return

    db_manager.create_tables()

    experiments = db_manager.get_experiments()

    if not experiments:
        print("[ERROR] No experiments found in registry")
        return

    all_results = []

    for exp in experiments:
        results = run_isolation_forest(exp["name"], contamination)
        all_results.extend(results)

    if all_results:
        save_results(all_results)

    print("\n=== DONE ===")


if __name__ == "__main__":
    main()