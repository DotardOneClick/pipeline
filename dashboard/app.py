import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from pathlib import Path

st.set_page_config(
    page_title="Log Intelligence Pipeline",
    page_icon="⬛",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown("""
<style>
    .main { background-color: #0e1117; }
    .block-container { padding-top: 1.5rem; }
    h1, h2, h3 { color: #e0e0e0; font-family: 'Courier New', monospace; }
    .metric-container { background: #1a1d27; border-left: 3px solid #4a9eff; padding: 1rem; border-radius: 4px; }
    .stMetric label { color: #888; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 1px; }
    .stMetric value { color: #e0e0e0; }
    div[data-testid="stSidebar"] { background-color: #13151f; }
</style>
""", unsafe_allow_html=True)

PLOTLY_THEME = dict(
    template="plotly_dark",
    paper_bgcolor="#0e1117",
    plot_bgcolor="#0e1117",
    font=dict(family="Courier New, monospace", color="#c0c0c0", size=11),
    margin=dict(l=40, r=20, t=40, b=40),
)

ACCENT   = "#4a9eff"
WARN     = "#f0a500"
CRITICAL = "#e05555"
OK       = "#4caf82"

#data loader
ROOT      = Path(__file__).parents[1]
PROCESSED = ROOT / "data" / "processed"
METRICS   = PROCESSED / "metrics"


@st.cache_data
def load_csv(path: Path) -> pd.DataFrame:
    if path.exists():
        return pd.read_csv(path)
    return pd.DataFrame()


def load_all() -> dict:
    return {
        "events":           load_csv(PROCESSED / "events.csv"),
        "errors":           load_csv(PROCESSED / "errors.csv"),
        "devices":          load_csv(PROCESSED / "devices.csv"),
        "volume":           load_csv(METRICS / "event_volume_hourly.csv"),
        "error_rate":       load_csv(METRICS / "error_rate_by_device.csv"),
        "top_errors":       load_csv(METRICS / "top_error_code.csv"),
        "mtbe":             load_csv(METRICS / "mtb_by_device.csv"),
        "health":           load_csv(METRICS / "device_health_score.csv"),
        "zscore":           load_csv(METRICS / "anomalies_zscore.csv"),
        "rolling":          load_csv(METRICS / "anomalies_rolling.csv"),
        "anomaly_devices":  load_csv(METRICS / "anomalies_devices.csv"),
    }

#sidebar
def render_sidebar(data: dict) -> str:
    with st.sidebar:
        st.markdown("## `LOG INTELLIGENCE`")
        st.markdown("---")
        page = st.radio(
            "Navigation",
            ["Overview", "Device Health", "Error Analysis", "Anomaly Detection", "Troubleshooting"],
            label_visibility="collapsed",
        )
        st.markdown("---")
        if not data["events"].empty:
            st.markdown("**Pipeline status**")
            st.markdown(f"`events:` **{len(data['events']):,}**")
            st.markdown(f"`errors:` **{len(data['errors']):,}**")
            st.markdown(f"`devices:` **{len(data['devices']):,}**")
        st.markdown("---")
        st.markdown("<small>GlobalLogic Internship Task</small>", unsafe_allow_html=True)
    return page

#pages
def page_overview(data: dict):
    st.title("Overview")
    st.markdown("##### Event volume and pipeline summary")

    events = data["events"]
    errors = data["errors"]

    #KPI row
    col1, col2, col3, col4 = st.columns(4)
    total = len(events)
    n_errors = len(events[events["event_type"] == "error"]) if not events.empty else 0
    n_warnings = len(events[events["event_type"] == "warning"]) if not events.empty else 0
    error_rate = round(100 * n_errors / total, 2) if total else 0

    col1.metric("Total Events", f"{total:,}")
    col2.metric("Errors", f"{n_errors:,}")
    col3.metric("Warnings", f"{n_warnings:,}")
    col4.metric("Error Rate", f"{error_rate}%")

    st.markdown("---")

    # event volume over time
    volume = data["volume"]
    if not volume.empty:
        st.markdown("#### Event Volume — Hourly Distribution")
        fig = px.area(
            volume,
            x="hour",
            y="event_count",
            color="event_type",
            color_discrete_map={
                "info": OK,
                "warning": WARN,
                "error": CRITICAL,
            },
            #**{k: v for k, v in PLOTLY_THEME.items() if k != "template"},
            template="plotly_dark",
        )
        fig.update_layout(**{k: v for k, v in PLOTLY_THEME.items()})
        fig.update_xaxes(showgrid=False)
        fig.update_yaxes(showgrid=True, gridcolor="#1e2130")
        st.plotly_chart(fig, use_container_width=True)

    # duration distribution
    if not events.empty and "duration_ms" in events.columns:
        st.markdown("#### Response Duration Distribution by Event Type")
        fig2 = px.box(
            events.dropna(subset=["duration_ms"]),
            x="event_type",
            y="duration_ms",
            color="event_type",
            color_discrete_map={
                "info": OK,
                "warning": WARN,
                "error": CRITICAL,
            },
            template="plotly_dark",
            points="outliers",
        )
        fig2.update_layout(**PLOTLY_THEME)
        fig2.update_xaxes(showgrid=False)
        fig2.update_yaxes(showgrid=True, gridcolor="#1e2130", title="duration (ms)")
        st.plotly_chart(fig2, use_container_width=True)


def page_device_health(data: dict):
    st.title("Device Health")
    st.markdown("##### Health scores and error rates across all devices")

    health = data["health"]
    error_rate = data["error_rate"]

    if not health.empty:
        # health score [horizontal bar]
        st.markdown("#### Device Health Score `(0 = critical, 100 = healthy)`")
        health_sorted = health.sort_values("health_score")
        colors = [
            CRITICAL if s < 70 else WARN if s < 85 else OK
            for s in health_sorted["health_score"]
        ]
        fig = go.Figure(go.Bar(
            x=health_sorted["health_score"],
            y=health_sorted["device_id"],
            orientation="h",
            marker_color=colors,
            text=health_sorted["health_score"].astype(str),
            textposition="outside",
        ))
        fig.update_layout(
            **PLOTLY_THEME,
            height=700,
            xaxis_title="health score",
            yaxis_title="",
            showlegend=False,
        )
        fig.update_xaxes(range=[0, 110], showgrid=True, gridcolor="#1e2130")
        fig.update_yaxes(showgrid=False, tickfont=dict(size=9))
        st.plotly_chart(fig, use_container_width=True)

    if not error_rate.empty:
        # error rate heatmap per device
        st.markdown("#### Error / Warning Breakdown per Device")
        fig2 = px.scatter(
            error_rate,
            x="total_events",
            y="error_rate_pct",
            text="device_id",
            color="error_rate_pct",
            color_continuous_scale=["#4caf82", "#f0a500", "#e05555"],
            template="plotly_dark",
            size="error_count",
            size_max=20,
        )
        fig2.update_traces(textposition="top center", textfont_size=8)
        fig2.update_layout(
            **PLOTLY_THEME,
            xaxis_title="total events",
            yaxis_title="error rate (%)",
            coloraxis_showscale=False,
        )
        fig2.update_xaxes(showgrid=True, gridcolor="#1e2130")
        fig2.update_yaxes(showgrid=True, gridcolor="#1e2130")
        st.plotly_chart(fig2, use_container_width=True)


def page_error_analysis(data: dict):
    st.title("Error Analysis")
    st.markdown("##### Error code frequency and mean time between errors")

    top_errors = data["top_errors"]
    mtbe = data["mtbe"]

    col1, col2 = st.columns(2)

    with col1:
        if not top_errors.empty:
            st.markdown("#### Top Error Codes")
            fig = px.bar(
                top_errors.sort_values("occurrences"),
                x="occurrences",
                y="error_code",
                orientation="h",
                color="occurrences",
                color_continuous_scale=["#1e2130", CRITICAL],
                text="occurrences",
                template="plotly_dark",
            )
            fig.update_layout(
                **PLOTLY_THEME,
                showlegend=False,
                coloraxis_showscale=False,
                xaxis_title="occurrences",
                yaxis_title="",
            )
            fig.update_xaxes(showgrid=True, gridcolor="#1e2130")
            fig.update_yaxes(showgrid=False)
            st.plotly_chart(fig, use_container_width=True)

    with col2:
        if not mtbe.empty:
            st.markdown("#### MTBE — Mean Time Between Errors `(minutes)`")
            fig2 = px.bar(
                mtbe.sort_values("mtbe_minutes").head(20),
                x="mtbe_minutes",
                y="device_id",
                orientation="h",
                color="mtbe_minutes",
                color_continuous_scale=["#e05555", "#f0a500", "#4caf82"],
                text="mtbe_minutes",
                template="plotly_dark",
            )
            fig2.update_layout(
                **PLOTLY_THEME,
                showlegend=False,
                coloraxis_showscale=False,
                xaxis_title="minutes between errors",
                yaxis_title="",
                title="top 20 most frequent error devices",
            )
            fig2.update_xaxes(showgrid=True, gridcolor="#1e2130")
            fig2.update_yaxes(showgrid=False, tickfont=dict(size=9))
            st.plotly_chart(fig2, use_container_width=True)

    # Error heatmap [device vs error code]
    errors = data["errors"]
    if not errors.empty and "error_code" in errors.columns:
        st.markdown("#### Error Code × Device Heatmap")
        pivot = errors.groupby(["device_id", "error_code"]).size().reset_index(name="count")
        pivot_wide = pivot.pivot(index="device_id", columns="error_code", values="count").fillna(0)
        fig3 = px.imshow(
            pivot_wide,
            color_continuous_scale=["#0e1117", "#1e2a40", ACCENT, CRITICAL],
            template="plotly_dark",
            aspect="auto",
        )
        fig3.update_layout(**PLOTLY_THEME, height=500)
        fig3.update_xaxes(showgrid=False)
        fig3.update_yaxes(showgrid=False, tickfont=dict(size=8))
        st.plotly_chart(fig3, use_container_width=True)


def page_anomaly(data: dict):
    st.title("Anomaly Detection")
    st.markdown("##### Z-score and rolling average based spike detection")

    zscore = data["zscore"]
    anomaly_devices = data["anomaly_devices"]

    if not zscore.empty:
        st.markdown("#### Hourly Error Count with Z-score Anomalies")

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=zscore["hour"],
            y=zscore["error_count"],
            mode="lines+markers",
            name="error count",
            line=dict(color=ACCENT, width=1.5),
            marker=dict(size=4),
        ))
        fig.add_trace(go.Scatter(
            x=zscore["hour"],
            y=zscore["mean_errors"],
            mode="lines",
            name="mean",
            line=dict(color="#555", width=1, dash="dash"),
        ))

        # anomaly markers
        anomalies = zscore[zscore["is_anomaly"] == True]
        if not anomalies.empty:
            fig.add_trace(go.Scatter(
                x=anomalies["hour"],
                y=anomalies["error_count"],
                mode="markers",
                name="anomaly",
                marker=dict(color=CRITICAL, size=10, symbol="x"),
            ))

        fig.update_layout(
            **PLOTLY_THEME,
            xaxis_title="hour",
            yaxis_title="error count",
            legend=dict(orientation="h", y=1.1),
        )
        fig.update_xaxes(showgrid=False)
        fig.update_yaxes(showgrid=True, gridcolor="#1e2130")
        st.plotly_chart(fig, use_container_width=True)

        # Z-score distribution
        st.markdown("#### Z-score Distribution")
        fig2 = px.bar(
            zscore,
            x="hour",
            y="z_score",
            color="is_anomaly",
            color_discrete_map={True: CRITICAL, False: ACCENT},
            template="plotly_dark",
        )
        fig2.add_hline(y=1.0, line_dash="dash", line_color=WARN, annotation_text="threshold")
        fig2.add_hline(y=-1.0, line_dash="dash", line_color=WARN)
        fig2.update_layout(**PLOTLY_THEME, xaxis_title="hour", yaxis_title="z-score")
        fig2.update_xaxes(showgrid=False)
        fig2.update_yaxes(showgrid=True, gridcolor="#1e2130")
        st.plotly_chart(fig2, use_container_width=True)

    if not anomaly_devices.empty:
        st.markdown("#### Anomalous Devices by Error Count")
        fig3 = px.scatter(
            anomaly_devices,
            x="device_id",
            y="error_count",
            color="is_anomaly",
            color_discrete_map={True: CRITICAL, False: ACCENT},
            size="error_count",
            size_max=25,
            text="device_id",
            template="plotly_dark",
        )
        fig3.update_traces(textposition="top center", textfont_size=8)
        fig3.update_layout(
            **PLOTLY_THEME,
            xaxis_title="",
            yaxis_title="error count",
            showlegend=True,
            xaxis=dict(showticklabels=False),
        )
        fig3.update_yaxes(showgrid=True, gridcolor="#1e2130")
        st.plotly_chart(fig3, use_container_width=True)


def page_troubleshooting(data: dict):
    st.title("Troubleshooting")
    st.markdown("##### Most problematic devices and recent error log")

    health = data["health"]
    errors = data["errors"]

    if not health.empty:
        st.markdown("#### Critical Devices `health score < 80`")
        critical = health[health["health_score"] < 80].sort_values("health_score")

        if critical.empty:
            st.info("No critical devices detected.")
        else:
            for _, row in critical.iterrows():
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Device", row["device_id"])
                col2.metric("Health", f"{row['health_score']}")
                col3.metric("Errors", f"{int(row['errors'])}")
                col4.metric("Warnings", f"{int(row['warnings'])}")

    st.markdown("---")

    if not errors.empty:
        st.markdown("#### Recent Error Log")

        # filters
        col1, col2 = st.columns(2)
        with col1:
            selected_devices = st.multiselect(
                "Filter by device",
                options=sorted(errors["device_id"].unique()),
                default=[],
            )
        with col2:
            selected_codes = st.multiselect(
                "Filter by error code",
                options=sorted(errors["error_code"].dropna().unique()),
                default=[],
            )

        filtered = errors.copy()
        if selected_devices:
            filtered = filtered[filtered["device_id"].isin(selected_devices)]
        if selected_codes:
            filtered = filtered[filtered["error_code"].isin(selected_codes)]

        filtered = filtered.sort_values("timestamp", ascending=False).head(200)

        st.dataframe(
            filtered[["timestamp", "device_id", "event_type", "error_code", "message", "duration_ms"]],
            use_container_width=True,
            height=400,
        )


def main():
    data = load_all()
    page = render_sidebar(data)

    if page == "Overview":
        page_overview(data)
    elif page == "Device Health":
        page_device_health(data)
    elif page == "Error Analysis":
        page_error_analysis(data)
    elif page == "Anomaly Detection":
        page_anomaly(data)
    elif page == "Troubleshooting":
        page_troubleshooting(data)


if __name__ == "__main__":
    main()