import logging
from pathlib import Path
import duckdb

#logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(Path(__file__).parents[1] / "logs" / "analytics.log"),
    ],
)
log = logging.getLogger(__name__)

#path
ROOT = Path(__file__).parents[1]
PROCESSED = ROOT / "data" / "processed"
METRICS = ROOT / "data" / "processed" / "metrics"
EVENTS_CSV = str(PROCESSED / "events.csv")
ERRORS_CSV = str(PROCESSED / "errors.csv")

#query
QUERIES = {

    "event_volume_hourly": """
        SELECT
            strftime(timestamp::TIMESTAMP, '%Y-%m-%d %H:00') AS hour,
            event_type,
            COUNT(*) AS event_count
        FROM read_csv_auto('{events}')
        GROUP BY hour, event_type
        ORDER BY hour
    """, 

    "error_rate_by_device": """
        SELECT
            device_id,
            COUNT(*) AS total_events,
            SUM (CASE WHEN event_type = 'error' THEN 1 ELSE 0 END) AS error_count,
            ROUND (
                100.0 * SUM(CASE WHEN event_type = 'error' THEN 1 ELSE 0 END) / COUNT(*), 2) AS error_rate_pct
        FROM read_csv_auto('{events}')
        GROUP BY device_id
        ORDER BY error_rate_pct DESC
    """, 

    "top_error_code": """
        SELECT
            error_code,
            COUNT(*) AS occurrences,
            COUNT(DISTINCT device_id) AS affected_devices
        FROM read_csv_auto('{errors}')
        GROUP BY error_code
        ORDER BY occurrences DESC
    """, 

    "mtb_by_device": """
        WITH ordered_errors AS (
            SELECT
                device_id,
                timestamp::TIMESTAMP AS ts,
                LAG(timestamp::TIMESTAMP) OVER (PARTITION BY device_id ORDER BY timestamp::TIMESTAMP) AS prev_ts
                FROM read_csv_auto('{errors}')
        ),
        time_diffs AS (
            SELECT 
                device_id,
                EPOCH(ts - prev_ts) / 60.0 AS minutes_between
            FROM ordered_errors
            WHERE prev_ts IS NOT NULL
        )
        SELECT
            device_id,
            ROUND(AVG(minutes_between), 2) AS mtbe_minutes,
            COUNT(*) AS error_count
        FROM time_diffs
        GROUP BY device_id
        ORDER BY mtbe_minutes ASC
    """, 

    "device_health_score": """
        WITH stats AS (
            SELECT
                device_id,
                COUNT(*) AS total_events,
                SUM(CASE WHEN event_type = 'error' THEN 1 ELSE 0 END) AS errors,
                SUM(CASE WHEN event_type = 'warning' THEN 1 ELSE 0 END) AS warnings,
                ROUND(AVG(duration_ms), 2) AS avg_duration_ms
            FROM read_csv_auto('{events}')
            GROUP BY device_id
        )
        SELECT 
            device_id,
            total_events,
            errors,
            warnings,
            avg_duration_ms,
            ROUND(
            100.0 * (1.0 - (errors * 2.0 + warnings * 0.5) / 
            NULLIF(total_events * 2.0, 0)), 2) AS health_score
            FROM stats
            ORDER BY health_score ASC
    """, 

    "error_spikes": """
        WITH hourly AS (
            SELECT
                strftime(timestamp::TIMESTAMP, '%Y-%m-%d %H:00') AS hour,
                COUNT(*) AS error_count
            FROM read_csv_auto('{errors}')
            GROUP BY hour
        ),
        stats AS (
            SELECT
                AVG(error_count) AS mean_errors,
                STDDEV(error_count) AS std_errors
            FROM hourly
        )
        SELECT
            h.hour,
            h.error_count,
            ROUND(s.mean_errors, 2) AS mean_errors,
            ROUND(s.std_errors, 2) AS std_errors,
            ROUND ((h.error_count - s.mean_errors) / NULLIF(s.std_errors, 0), 2) AS z_score
        FROM hourly h , stats s
        WHERE (h.error_count - s.mean_errors) / NULLIF(s.std_errors, 0) > 1.0
        ORDER BY h.hour
    """,
}

#runner
def run_metrics(
        events_csv: str = EVENTS_CSV,
        errors_csv: str = ERRORS_CSV,
        metrics_dir: Path = METRICS,
) -> dict:
    log.info("===== Analytics Started =====")
    metrics_dir.mkdir(parents=True, exist_ok=True)

    conn = duckdb.connect()
    results = {}

    for name, sql in QUERIES.items():
        try:
            query = sql.format(events=events_csv, errors=errors_csv)
            df = conn.execute(query).df()
            out_path = metrics_dir / f"{name}.csv"
            df.to_csv(out_path, index=False)
            log.info(f"{name}: {len(df)} rows -> {out_path.name}")
            results[name] = df
        except Exception as e:
            log.error(f"{name} failed: {e}")

    conn.close()
    log.info("===== Analytics Completed =====")
    return results


if __name__ == "__main__": 
    print("Running. . .")
    run_metrics()