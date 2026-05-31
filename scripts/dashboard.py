# dashboard.py
import streamlit as st
import sqlite3
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from pathlib import Path
from datetime import datetime

# ----------------------------
# CONFIG
# ----------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH      = PROJECT_ROOT / "databases" / "jitter.db"
DASHBOARD_DIR = PROJECT_ROOT / "dashboard"
DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)

EXPERIMENT_COLORS = {
    "baseline":     "#00f5d4",
    "stress_test":  "#f72585",
    "cpu_pinned_0": "#4895ef",
}

# ----------------------------
# PAGE CONFIG
# ----------------------------
st.set_page_config(
    page_title="Runtime Jitter Monitor",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ----------------------------
# THEME
# ----------------------------
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Space+Grotesk:wght@300;400;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Space Grotesk', sans-serif;
        background-color: #0a0a0f;
        color: #e0e0e0;
    }

    .stApp { background-color: #0a0a0f; }

    h1, h2, h3 {
        font-family: 'JetBrains Mono', monospace;
        color: #00f5d4;
        letter-spacing: -0.5px;
    }

    .metric-card {
        background: #12121a;
        border: 1px solid #1e1e2e;
        border-radius: 8px;
        padding: 16px 20px;
        margin-bottom: 12px;
    }

    .metric-value {
        font-family: 'JetBrains Mono', monospace;
        font-size: 1.6rem;
        font-weight: 700;
        color: #00f5d4;
    }

    .metric-label {
        font-size: 0.75rem;
        color: #666;
        text-transform: uppercase;
        letter-spacing: 1px;
    }

    .status-bar {
        background: #12121a;
        border-left: 3px solid #00f5d4;
        padding: 8px 16px;
        margin-bottom: 24px;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.8rem;
        color: #666;
    }

    section[data-testid="stSidebar"] {
        background-color: #0d0d14;
        border-right: 1px solid #1e1e2e;
    }

    .stSelectbox label, .stSlider label, .stMultiSelect label {
        color: #888 !important;
        font-size: 0.75rem !important;
        text-transform: uppercase;
        letter-spacing: 1px;
    }

    .block-container { padding-top: 2rem; }
</style>
""", unsafe_allow_html=True)


# ----------------------------
# HELPERS
# ----------------------------
def hex_to_rgba(hex_color, alpha=0.2):
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    return f"rgba({r},{g},{b},{alpha})"


def db_available():
    return DB_PATH.exists()


def get_connection():
    return sqlite3.connect(DB_PATH)


def load_runs():
    con = get_connection()
    df  = pd.read_sql_query("""
        SELECT id, experiment_name, timestamp, os, cpu,
               num_runs, stress_mode, cpu_pinned
        FROM runs
        ORDER BY timestamp DESC
    """, con)
    con.close()
    return df


def load_measurements(experiment_names, limit_runs=None):
    con          = get_connection()
    placeholders = ",".join("?" * len(experiment_names))

    query = f"""
        SELECT r.experiment_name, r.timestamp, r.id as run_id,
               m.run_number, m.time_seconds
        FROM runs r
        JOIN measurements m ON r.id = m.run_id
        WHERE r.experiment_name IN ({placeholders})
        ORDER BY r.timestamp DESC, m.run_number ASC
    """

    df = pd.read_sql_query(query, con, params=experiment_names)
    con.close()

    if limit_runs:
        run_ids = df["run_id"].unique()[:limit_runs]
        df      = df[df["run_id"].isin(run_ids)]

    return df


def load_run_stats(experiment_names):
    con          = get_connection()
    placeholders = ",".join("?" * len(experiment_names))

    query = f"""
        SELECT
            r.experiment_name,
            r.timestamp,
            r.id as run_id,
            AVG(m.time_seconds) as mean,
            MIN(m.time_seconds) as min,
            MAX(m.time_seconds) as max,
            COUNT(m.time_seconds) as n
        FROM runs r
        JOIN measurements m ON r.id = m.run_id
        WHERE r.experiment_name IN ({placeholders})
        GROUP BY r.id
        ORDER BY r.timestamp ASC
    """

    df = pd.read_sql_query(query, con, params=experiment_names)
    con.close()
    return df


# ----------------------------
# LOAD STATISTICAL TEST RESULTS
# Pulls the most recent pairwise test result for each pair
# from the statistical_tests table written by stats.py.
# ----------------------------
def load_stats_results():
    con = get_connection()
    try:
        df = pd.read_sql_query("""
            SELECT
                experiment_a, experiment_b,
                n_a, n_b,
                mean_a, mean_b,
                ci_a_low, ci_a_high,
                ci_b_low, ci_b_high,
                welch_p, mannwhitney_p,
                cohens_d, effect_size,
                significant, created_at
            FROM statistical_tests
            ORDER BY created_at DESC
        """, con)
    except Exception:
        df = pd.DataFrame()
    con.close()
    return df


# ----------------------------
# LOAD ANOMALY RESULTS
# Pulls all anomaly flags from the most recent scan,
# ordered by experiment and anomaly score ascending so
# the most anomalous runs appear at the top of each group.
# ----------------------------
def load_anomaly_results():
    con = get_connection()
    try:
        df = pd.read_sql_query("""
            SELECT
                run_id, experiment_name, contamination,
                anomaly_score, z_score,
                is_anomaly, z_score_flag, high_confidence,
                features_json, created_at
            FROM anomaly_flags
            ORDER BY experiment_name ASC, anomaly_score ASC
        """, con)
    except Exception:
        df = pd.DataFrame()
    con.close()
    return df


# ----------------------------
# SIDEBAR
# ----------------------------
with st.sidebar:
    st.markdown("## ⚡ Controls")

    refresh_interval = st.slider(
        "Auto-refresh (seconds)",
        min_value=5, max_value=60, value=10, step=5
    )

    all_experiments    = ["baseline", "stress_test", "cpu_pinned_0"]
    selected_experiments = st.multiselect(
        "Experiments",
        options=all_experiments,
        default=all_experiments
    )

    limit_runs = st.slider(
        "Recent runs to show",
        min_value=1, max_value=20, value=5
    )

    st.markdown("---")
    st.markdown(f"""
    <div style='font-family: JetBrains Mono, monospace; font-size: 0.7rem; color: #444;'>
        DB: {DB_PATH.name}<br>
        Refreshing every {refresh_interval}s
    </div>
    """, unsafe_allow_html=True)


# ----------------------------
# AUTO REFRESH
# ----------------------------
st.markdown(f"""
<script>
    setTimeout(function() {{
        window.location.reload();
    }}, {refresh_interval * 1000});
</script>
""", unsafe_allow_html=True)


# ----------------------------
# HEADER
# ----------------------------
st.markdown("# ⚡ Runtime Jitter Monitor")
st.markdown(f"""
<div class='status-bar'>
    Last updated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} &nbsp;|&nbsp;
    DB: {str(DB_PATH)} &nbsp;|&nbsp;
    Watching: {", ".join(selected_experiments) if selected_experiments else "none"}
</div>
""", unsafe_allow_html=True)


# ----------------------------
# DB CHECK
# ----------------------------
if not db_available():
    st.error("Database not found. Run the pipeline first to generate data.")
    st.code("python scripts/batch_run.py")
    st.stop()

if not selected_experiments:
    st.warning("Select at least one experiment from the sidebar.")
    st.stop()


# ----------------------------
# LOAD DATA
# ----------------------------
runs_df          = load_runs()
measurements_df  = load_measurements(selected_experiments, limit_runs=limit_runs)
stats_df         = load_run_stats(selected_experiments)
test_results_df  = load_stats_results()
anomaly_df       = load_anomaly_results()

if measurements_df.empty:
    st.warning("No data found for selected experiments. Run the pipeline to generate data.")
    st.stop()


# ----------------------------
# ROW 1: SUMMARY STATS CARDS
# Includes 95% CI from the statistical_tests table when
# available, falling back gracefully if stats haven't run.
# ----------------------------
st.markdown("## 📊 Summary Statistics")

cols = st.columns(len(selected_experiments))

for i, exp in enumerate(selected_experiments):
    exp_data = measurements_df[measurements_df["experiment_name"] == exp]["time_seconds"]

    if exp_data.empty:
        continue

    color = EXPERIMENT_COLORS.get(exp, "#ffffff")

    # Pull CI from stats table if available
    ci_low, ci_high = None, None
    if not test_results_df.empty:
        row_a = test_results_df[test_results_df["experiment_a"] == exp]
        row_b = test_results_df[test_results_df["experiment_b"] == exp]
        if not row_a.empty:
            ci_low  = row_a.iloc[0]["ci_a_low"]
            ci_high = row_a.iloc[0]["ci_a_high"]
        elif not row_b.empty:
            ci_low  = row_b.iloc[0]["ci_b_low"]
            ci_high = row_b.iloc[0]["ci_b_high"]

    ci_str = (
        f"{ci_low:.5f} – {ci_high:.5f}"
        if ci_low is not None
        else "run stats.py"
    )

    with cols[i]:
        st.markdown(f"""
        <div class='metric-card' style='border-top: 3px solid {color};'>
            <div style='color: {color}; font-family: JetBrains Mono, monospace;
                        font-size: 0.8rem; font-weight: 700; margin-bottom: 12px;
                        text-transform: uppercase; letter-spacing: 1px;'>
                {exp}
            </div>
            <div style='display: grid; grid-template-columns: 1fr 1fr; gap: 12px;'>
                <div>
                    <div class='metric-label'>Mean</div>
                    <div class='metric-value' style='color: {color};'>{exp_data.mean():.4f}s</div>
                </div>
                <div>
                    <div class='metric-label'>Std Dev</div>
                    <div class='metric-value' style='color: {color};'>{exp_data.std():.4f}s</div>
                </div>
                <div>
                    <div class='metric-label'>P95</div>
                    <div class='metric-value' style='color: {color};'>{np.percentile(exp_data, 95):.4f}s</div>
                </div>
                <div>
                    <div class='metric-label'>P99</div>
                    <div class='metric-value' style='color: {color};'>{np.percentile(exp_data, 99):.4f}s</div>
                </div>
                <div>
                    <div class='metric-label'>Min</div>
                    <div class='metric-value' style='color: {color};'>{exp_data.min():.4f}s</div>
                </div>
                <div>
                    <div class='metric-label'>Max</div>
                    <div class='metric-value' style='color: {color};'>{exp_data.max():.4f}s</div>
                </div>
            </div>
            <div style='margin-top: 14px; border-top: 1px solid #1e1e2e; padding-top: 10px;'>
                <div class='metric-label'>95% CI (mean)</div>
                <div style='font-family: JetBrains Mono, monospace; font-size: 0.85rem;
                            color: {color}; margin-top: 4px;'>
                    {ci_str}
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)


# ----------------------------
# ROW 2: DISTRIBUTION HISTOGRAM
# ----------------------------
st.markdown("## 📈 Runtime Distribution")

fig_hist = go.Figure()

for exp in selected_experiments:
    exp_data = measurements_df[measurements_df["experiment_name"] == exp]["time_seconds"]
    if exp_data.empty:
        continue

    fig_hist.add_trace(go.Histogram(
        x=exp_data, name=exp, nbinsx=60, opacity=0.7,
        marker_color=EXPERIMENT_COLORS.get(exp, "#ffffff")
    ))

fig_hist.update_layout(
    barmode="overlay",
    paper_bgcolor="#0a0a0f", plot_bgcolor="#12121a",
    font=dict(family="JetBrains Mono", color="#888"),
    legend=dict(bgcolor="#12121a", bordercolor="#1e1e2e"),
    xaxis=dict(title="Time (seconds)", gridcolor="#1e1e2e"),
    yaxis=dict(title="Frequency", gridcolor="#1e1e2e"),
    margin=dict(l=40, r=40, t=20, b=40)
)

st.plotly_chart(fig_hist, width="stretch")


# ----------------------------
# ROW 3: BOXPLOT COMPARISON
# ----------------------------
st.markdown("## 📦 Variability Comparison")

fig_box = go.Figure()

for exp in selected_experiments:
    exp_data = measurements_df[measurements_df["experiment_name"] == exp]["time_seconds"]
    if exp_data.empty:
        continue

    color = EXPERIMENT_COLORS.get(exp, "#ffffff")

    fig_box.add_trace(go.Box(
        y=exp_data, name=exp,
        marker_color=color, line_color=color,
        fillcolor=hex_to_rgba(color, 0.2)
    ))

fig_box.update_layout(
    paper_bgcolor="#0a0a0f", plot_bgcolor="#12121a",
    font=dict(family="JetBrains Mono", color="#888"),
    legend=dict(bgcolor="#12121a", bordercolor="#1e1e2e"),
    yaxis=dict(title="Time (seconds)", gridcolor="#1e1e2e"),
    margin=dict(l=40, r=40, t=20, b=40)
)

st.plotly_chart(fig_box, width="stretch")


# ----------------------------
# ROW 4: TAIL LATENCY
# ----------------------------
st.markdown("## 🎯 Tail Latency")

fig_tail = go.Figure()

for exp in selected_experiments:
    exp_data = measurements_df[measurements_df["experiment_name"] == exp]["time_seconds"]
    if exp_data.empty:
        continue

    fig_tail.add_trace(go.Scatter(
        x=["P50", "P95", "P99"],
        y=[
            np.percentile(exp_data, 50),
            np.percentile(exp_data, 95),
            np.percentile(exp_data, 99),
        ],
        mode="lines+markers", name=exp,
        line=dict(color=EXPERIMENT_COLORS.get(exp, "#ffffff"), width=2),
        marker=dict(size=8)
    ))

fig_tail.update_layout(
    paper_bgcolor="#0a0a0f", plot_bgcolor="#12121a",
    font=dict(family="JetBrains Mono", color="#888"),
    legend=dict(bgcolor="#12121a", bordercolor="#1e1e2e"),
    yaxis=dict(title="Time (seconds)", gridcolor="#1e1e2e"),
    xaxis=dict(gridcolor="#1e1e2e"),
    margin=dict(l=40, r=40, t=20, b=40)
)

st.plotly_chart(fig_tail, width="stretch")


# ----------------------------
# ROW 5: HISTORICAL TREND
# ----------------------------
st.markdown("## 🕐 Historical Mean Jitter Per Run")

fig_trend = go.Figure()

for exp in selected_experiments:
    exp_stats = stats_df[stats_df["experiment_name"] == exp]
    if exp_stats.empty:
        continue

    fig_trend.add_trace(go.Scatter(
        x=exp_stats["timestamp"], y=exp_stats["mean"],
        mode="lines+markers", name=exp,
        line=dict(color=EXPERIMENT_COLORS.get(exp, "#ffffff"), width=2),
        marker=dict(size=6)
    ))

fig_trend.update_layout(
    paper_bgcolor="#0a0a0f", plot_bgcolor="#12121a",
    font=dict(family="JetBrains Mono", color="#888"),
    legend=dict(bgcolor="#12121a", bordercolor="#1e1e2e"),
    xaxis=dict(title="Run Timestamp", gridcolor="#1e1e2e"),
    yaxis=dict(title="Mean Time (seconds)", gridcolor="#1e1e2e"),
    margin=dict(l=40, r=40, t=20, b=40)
)

st.plotly_chart(fig_trend, width="stretch")


# ----------------------------
# ROW 6: STATISTICAL TEST RESULTS
# Live pairwise hypothesis test results from stats.py.
# Each pair shows both p-values, Cohen's d, effect size,
# means with CIs, and a clear significant / not significant
# verdict highlighted in the appropriate color.
# ----------------------------
st.markdown("## 🧪 Statistical Hypothesis Tests")

if test_results_df.empty:
    st.markdown("""
    <div class='metric-card' style='border-top: 3px solid #444;
         text-align: center; padding: 30px;'>
        <div style='color: #444; font-size: 0.85rem;'>
            No test results yet — run the pipeline to generate
            statistical comparisons.
        </div>
    </div>
    """, unsafe_allow_html=True)
else:
    for _, row in test_results_df.iterrows():
        sig       = bool(row["significant"])
        sig_color = "#f72585" if sig else "#444"
        sig_label = "SIGNIFICANT" if sig else "NOT SIGNIFICANT"

        col_a_color = EXPERIMENT_COLORS.get(row["experiment_a"], "#ffffff")
        col_b_color = EXPERIMENT_COLORS.get(row["experiment_b"], "#ffffff")

        st.markdown(f"""
        <div class='metric-card' style='border-top: 3px solid {sig_color};'>
            <div style='display: flex; justify-content: space-between;
                        align-items: center; margin-bottom: 14px;'>
                <div style='font-family: JetBrains Mono, monospace; font-size: 0.85rem;'>
                    <span style='color: {col_a_color};'>{row['experiment_a']}</span>
                    <span style='color: #444;'> vs </span>
                    <span style='color: {col_b_color};'>{row['experiment_b']}</span>
                </div>
                <div style='color: {sig_color}; font-family: JetBrains Mono, monospace;
                            font-size: 0.75rem; font-weight: 700; letter-spacing: 1px;'>
                    {sig_label}
                </div>
            </div>
            <div style='display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px;'>
                <div>
                    <div class='metric-label'>Welch p-value</div>
                    <div style='font-family: JetBrains Mono, monospace; font-size: 1rem;
                                color: {sig_color};'>{row['welch_p']:.5f}</div>
                </div>
                <div>
                    <div class='metric-label'>Mann-Whitney p</div>
                    <div style='font-family: JetBrains Mono, monospace; font-size: 1rem;
                                color: {sig_color};'>{row['mannwhitney_p']:.5f}</div>
                </div>
                <div>
                    <div class='metric-label'>Cohen's d</div>
                    <div style='font-family: JetBrains Mono, monospace; font-size: 1rem;
                                color: #e0e0e0;'>{row['cohens_d']:.4f}</div>
                </div>
                <div>
                    <div class='metric-label'>Effect Size</div>
                    <div style='font-family: JetBrains Mono, monospace; font-size: 1rem;
                                color: #e0e0e0;'>{row['effect_size']}</div>
                </div>
                <div>
                    <div class='metric-label'>Mean A (95% CI)</div>
                    <div style='font-family: JetBrains Mono, monospace; font-size: 0.8rem;
                                color: {col_a_color};'>
                        {row['mean_a']:.5f}<br>
                        <span style='color: #555; font-size: 0.7rem;'>
                            [{row['ci_a_low']:.5f}, {row['ci_a_high']:.5f}]
                        </span>
                    </div>
                </div>
                <div>
                    <div class='metric-label'>Mean B (95% CI)</div>
                    <div style='font-family: JetBrains Mono, monospace; font-size: 0.8rem;
                                color: {col_b_color};'>
                        {row['mean_b']:.5f}<br>
                        <span style='color: #555; font-size: 0.7rem;'>
                            [{row['ci_b_low']:.5f}, {row['ci_b_high']:.5f}]
                        </span>
                    </div>
                </div>
                <div>
                    <div class='metric-label'>n (A / B)</div>
                    <div style='font-family: JetBrains Mono, monospace; font-size: 0.9rem;
                                color: #e0e0e0;'>{int(row['n_a'])} / {int(row['n_b'])}</div>
                </div>
                <div>
                    <div class='metric-label'>Last run</div>
                    <div style='font-family: JetBrains Mono, monospace; font-size: 0.7rem;
                                color: #444;'>{row['created_at'][:19]}</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)


# ----------------------------
# ROW 7: ML ANOMALY DETECTION
# Shows per-experiment anomaly flags from the most recent
# Isolation Forest scan. High-confidence flags (IF + Z-score
# both agree) are highlighted in pink. Single-method flags
# are shown in amber. Normal runs are summarised as a count.
# ----------------------------
st.markdown("## 🤖 ML Anomaly Detection")

if anomaly_df.empty:
    st.markdown("""
    <div class='metric-card' style='border-top: 3px solid #444;
         text-align: center; padding: 30px;'>
        <div style='color: #444; font-size: 0.85rem;'>
            No anomaly scans yet — run the pipeline and follow the
            contamination parameter prompt to activate ML detection.
        </div>
    </div>
    """, unsafe_allow_html=True)
else:
    for exp in selected_experiments:
        exp_anomalies = anomaly_df[anomaly_df["experiment_name"] == exp]

        if exp_anomalies.empty:
            continue

        color         = EXPERIMENT_COLORS.get(exp, "#ffffff")
        n_total       = len(exp_anomalies)
        n_flagged     = int(exp_anomalies["is_anomaly"].sum())
        n_hc          = int(exp_anomalies["high_confidence"].sum())
        contamination = exp_anomalies.iloc[0]["contamination"]

        st.markdown(f"""
        <div class='metric-card' style='border-top: 3px solid {color};
             margin-bottom: 8px;'>
            <div style='display: flex; justify-content: space-between;
                        align-items: center; margin-bottom: 12px;'>
                <div style='color: {color}; font-family: JetBrains Mono, monospace;
                            font-size: 0.85rem; font-weight: 700;
                            text-transform: uppercase; letter-spacing: 1px;'>
                    {exp}
                </div>
                <div style='font-family: JetBrains Mono, monospace;
                            font-size: 0.75rem; color: #444;'>
                    contamination={contamination}
                    &nbsp;|&nbsp; runs={n_total}
                    &nbsp;|&nbsp; flagged={n_flagged}
                    &nbsp;|&nbsp; high-confidence={n_hc}
                </div>
            </div>
        """, unsafe_allow_html=True)

        # Flagged runs first, most anomalous at top
        flagged = exp_anomalies[exp_anomalies["is_anomaly"] == 1]
        normal  = exp_anomalies[exp_anomalies["is_anomaly"] == 0]

        for _, row in flagged.iterrows():
            hc_label = "⚠ HIGH CONFIDENCE ANOMALY" if row["high_confidence"] else "ANOMALY"
            hc_color = "#f72585" if row["high_confidence"] else "#f9a825"

            st.markdown(f"""
            <div style='background: #1a0a10; border-left: 3px solid {hc_color};
                        padding: 10px 14px; margin-bottom: 6px; border-radius: 4px;'>
                <div style='display: flex; justify-content: space-between;'>
                    <div style='color: {hc_color}; font-family: JetBrains Mono, monospace;
                                font-size: 0.75rem; font-weight: 700;'>
                        {hc_label} &nbsp; run_id={int(row['run_id'])}
                    </div>
                    <div style='color: #555; font-family: JetBrains Mono, monospace;
                                font-size: 0.7rem;'>
                        score={row['anomaly_score']:.4f} &nbsp; z={row['z_score']:.2f}
                    </div>
                </div>
                <div style='color: #888; font-family: JetBrains Mono, monospace;
                            font-size: 0.7rem; margin-top: 6px;'>
                    {row['features_json']}
                </div>
            </div>
            """, unsafe_allow_html=True)

        if not normal.empty:
            st.markdown(f"""
            <div style='color: #444; font-family: JetBrains Mono, monospace;
                        font-size: 0.7rem; padding: 6px 0;'>
                {len(normal)} normal run(s) — no anomaly detected
            </div>
            """, unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)
