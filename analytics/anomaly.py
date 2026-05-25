import logging
from pathlib import Path
import duckdb
import pandas as pd

#logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(Path(__file__).parents[1] / "logs" / "analytics.log")],
)
log = logging.getLogger(__name__)

#path
ROOT = Path(__file__).parents[1]
PROCESSED = ROOT / "data" / "processed"
METRICS = ROOT / "data" / "processed" / "metrics"
EVENTS_CSV = str(PROCESSED / "events.csv")
ERRORS_CSV = str(PROCESSED / "errors.csv")

#hourly error counts
def load_hourly_errors(errors_csv: str) -> pd.DataFrame:
    conn = duckdb.connect()
    df = conn.execute(f"""
        SELECT
            strftime(timestamp::TIMESTAMP, '%Y-%m-%d %H:00') AS hour,
            COUNT(*) AS error_count
        FROM read_csv_auto('{errors_csv}')
        GROUP BY hour
        ORDER BY hour
    """).df()
    conn.close()
    log.info(f"loadded {len(df)} hourly buckets")
    return df

#z-score anomaly detection
def detect_zscore_anomalies(df: pd.DataFrame, threshold: float = 1.0) -> pd.DataFrame:
    mean = df["error_count"].mean()
    std = df["error_count"].std()

    df = df.copy()
    df["mean_errors"] = round(mean, 2)
    df["std_errors"] = round(std, 2)
    df["z_score"] = ((df["error_count"] - mean) / std).round(2)
    df["is_anomaly"] = df["z_score"].abs() > threshold 

    n_anomalies = df["is_anomaly"].sum()
    log.info(f"z-score amomalies detected: {n_anomalies} (threshold={threshold})")
    return df

#rolling anomaly
def detect_rolling_anomalies(
    df: pd.DataFrame,
    window: int = 3,
    threshold: float = 1.5,
) -> pd.DataFrame:
    df = df.copy().sort_values("hour").reset_index(drop=True)

    df["rolling_mean"] = df["error_count"].rolling(window, min_periods=1).mean().round(2)
    df["rolling_std"] = df["error_count"].rolling(window, min_periods=1).std().fillna(0).round(2)
    df["rolling_anomaly"] = df["error_count"] > (df["rolling_mean"] + threshold * df["rolling_std"])

    n_anomalies = df["rolling_anomaly"].sum()
    log.info(f"Rolling Anomalies Detected: {n_anomalies} (window={window}, treshold={threshold})")
    return df

#per-device anomaly summary
def device_anomaly_summary(errors_csv: str) -> pd.DataFrame:
    conn = duckdb.connect()
    df = conn.execute(f"""
        SELECT
            device_id,
            COUNT(*) AS error_count
            FROM read_csv_auto('{errors_csv}')
            GROUP BY device_id
            ORDER BY error_count DESC
    """).df()
    conn.close()

    mean = df["error_count"].mean()
    std = df["error_count"].std()

    df["z_score"] = ((df["error_count"] - mean) / std).round(2)
    df["is_anomaly"] = df["z_score"] > 1.0

    n_anomalies = df["is_anomaly"].sum()
    log.info(f"Anomalous Devices Detected: {n_anomalies}")
    return df

#runner [main]
def run_anomaly_detection(
        errors_csv: str = ERRORS_CSV,
        metrics_dir: Path = METRICS,
) -> dict:
    log.info(f"===== Anomaly Detection Started =====")
    metrics_dir.mkdir(parents=True, exist_ok=True)

    #hourly z-score
    hourly_df = load_hourly_errors(errors_csv)
    zscore_df = detect_zscore_anomalies(hourly_df, threshold=1.0)
    zscore_df.to_csv(metrics_dir / "anomalies_zscore.csv", index=False)
    log.info(f"Saved anomalies_zscore.csv ({len(zscore_df)} rows)")

    #rolling average
    rolling_df = detect_rolling_anomalies(hourly_df, window=3, threshold=1.5)
    rolling_df.to_csv(metrics_dir / "anomalies_rolling.csv", index=False)
    log.info(f"Saved anomalies_rolling.csv ({len(rolling_df)} rows)")

    #per-device
    device_df = device_anomaly_summary(errors_csv)
    device_df.to_csv(metrics_dir / "anomalies_devices.csv", index=False)
    log.info(f"Saved anomalies_devices.csv ({len(device_df)} rows)")

    log.info("===== Alert Simulation =====")

    # devices with high error rate
    if not device_df.empty:
        critical_devices = device_df[device_df["is_anomaly"] == True]
        for _, row in critical_devices.iterrows():
            log.warning(
                f"[ALERT] Device {row['device_id']} has anomalous error count: "
                f"{row['error_count']} (z-score={row['z_score']})"
            )

    # hourly error spikes
    if not zscore_df.empty:
        spikes = zscore_df[zscore_df["is_anomaly"] == True]
        for _, row in spikes.iterrows():
            log.warning(
                f"[ALERT] Error spike detected at {row['hour']}: "
                f"{row['error_count']} errors (z-score={row['z_score']})"
            )

    log.info(f"===== Alert Simulation completed =====")

    return {
        "zscore": zscore_df,
        "rolling": rolling_df,
        "devices": device_df,
    }

if __name__ == "__main__":
    run_anomaly_detection()