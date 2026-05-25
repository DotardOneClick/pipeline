from pathlib import Path
from prefect import flow, task, get_run_logger
from ingestion.log_generator import generate_logs
from etl.transformer import run_etl
from storage.db_loader import run_loader
from analytics.metrics import run_metrics
from analytics.anomaly import run_anomaly_detection

ROOT = Path(__file__).parents[1]
RAW_PATH = ROOT / "data" / "raw" / "device_logs.jsonl"
PROCESSED = ROOT / "data" / "processed"

#task
@task(name="Generate Logs", retries=2, retry_delay_seconds=5)
def task_generate_logs():
    logger = get_run_logger()
    logger.info("Generating Device Logs. . .")
    logs = generate_logs(n_records=10000, output_path=RAW_PATH)
    logger.info(f"Generated {len(logs):,} records")
    return len(logs)

@task(name="Run ETL", retries=2, retry_delay_seconds=5)
def task_run_etl():
    logger = get_run_logger()
    logger.info(f"Running ETL transformer. . .")
    summary = run_etl()
    logger.info(f"ETL complete: {summary}")
    return summary

@task(name="Load to PostgreSQL", retries=2, retry_delay_seconds=10)
def task_load_db():
    logger = get_run_logger()
    logger.info(f"Loading data to PostgreSQL. . .")
    summary = run_loader()
    logger.info(f"DB load complete: {summary}")
    return summary 

@task(name="Run Alanytics", retries=1, retry_delay_seconds=5)
def task_run_metrics():
    logger = get_run_logger()
    logger.info("Running Analytics Metrics. . .")
    results = run_metrics()
    logger.info(f"Metric complete: {list(results.keys())}")
    return list(results.keys())

@task(name="Run Anomaly Detection", retries=1, retry_delay_seconds=5)
def task_run_anomaly():
    logger = get_run_logger()
    logger.info("Running Anomaly Detection. . .")
    results = run_anomaly_detection()
    logger.info(f"Alomaly Detection Complete: {list(results.keys())}")
    return list(results.keys())

#flow
@flow(name="Log Intelligence Pipeline", log_prints=True)
def run_pipeline(generate_new_logs: bool = True):
    print("=" * 50)
    print("Log Intelligence Pipeline Starting. . .")
    print("=" * 50)

    #[1]generate logs
    if generate_new_logs:
        n_logs = task_generate_logs()
        print(f"[1/5] Generated {n_logs:,} logs")
    else:
        print("[1/5] Skipped log generation")

    #[2]ETL transform
    etl_summary = task_run_etl()
    print(f"[2/5] ETL complete: {etl_summary['clean']:,} clean records")

    #[3]load to PostgreSQL
    db_summary = task_load_db()
    print(f"[3/5] DB loaded: {db_summary['events']:,} events")

    #[4]run analytics
    metric_keys = task_run_metrics()
    print(f"[4/5] Metrics: {metric_keys}")

    #[5]anomaly detection
    anomaly_keys = task_run_anomaly()
    print(f"[5/5] Anomalies: {anomaly_keys}")

    print("=" * 50)
    print("Pipeline Completed Successfully")
    print("=" * 50)


if __name__ == "__main__":
    run_pipeline()