import csv
import json
import logging
from datetime import datetime
from pathlib import Path

#logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(Path(__file__).parents[1] / "logs" / "etl.log"),

    ],
)

log = logging.getLogger(__name__)

#paths
ROOT = Path(__file__).parents[1]
RAW_PATH = ROOT / "data" / "raw" / "device_logs.jsonl"
PROCESSED = ROOT / "data" / "processed"
FAILED_PATH = ROOT / "data" / "processed" / "failed_records.jsonl"

VALID_EVENT_TYPES = {"info", "warning", "error"}

#validation
def _is_valid_timestamp(value:str) -> bool:
    try:
        datetime.fromisoformat(value)
        return True
    except (ValueError, TypeError):
        return False
    
def validate_record(record:dict) -> tuple[bool, str]:
    if not record.get("log_id"):
        return False, "missing_log_id"
    if not record.get("device_id"):
        return False, "missing or null device_id"
    if not _is_valid_timestamp(record.get("timestamp", "")):
        return False, "invalid_timestamp"
    if record.get("event_type") not in VALID_EVENT_TYPES:
        return False, f"invalid event_type: {record.get("event_type")}"
    return True, "ok"

#normalization
def extract_device(record: dict) -> dict:
    return {
        "device_id": record["device_id"],
        "device_type": record.get("device_type", "unknown"), 
    }

def extract_event(record: dict) -> dict:
    payload = record.get("payload") or {}
    return {
        "log_id": record["log_id"],
        "timestamp": record["timestamp"],
        "device_id": record["device_id"],
        "event_type": record["event_type"],
        "message": record.get("message", ""),
        "duration_ms": payload.get("duration_ms"),
        "status": payload.get("status"),
        "session_id": payload.get("session_id"),
        "firmware": payload.get("firmware"),
    }  

def extract_error(record: dict) -> dict | None:
    payload = record.get("payload") or {}
    error_code = payload.get("error_code")
    if not error_code:
        return None
    return {
        "log_id":      record["log_id"],
        "timestamp":   record["timestamp"],
        "device_id":   record["device_id"],
        "event_type":  record["event_type"],
        "error_code":  error_code,
        "message":     record.get("message", ""),
        "duration_ms": payload.get("duration_ms"),
    }

#csv writing
def write_csv(rows: list[dict], path: Path) -> None:
    if not rows: 
        log.warning(f"No records to write for {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    log.info(f"saved {len(rows):,} rows -> {path.name}")

#main ETL function
def run_etl(
        raw_path: Path = RAW_PATH,
        processed_dir: Path = PROCESSED,
        failed_path: Path = FAILED_PATH,
) -> dict:
    log.info("===== ETL pipeline started =====")
    processed_dir.mkdir(parents=True, exist_ok=True)

    raw_records: list[dict] = []
    with open (raw_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    raw_records.append(json.loads(line))
                except json.JSONDecodeError as e:
                    log.warning(f"json parse error: {e}")
    log.info(f"total read: {len(raw_records):,}")

    seen_ids: set[str] = set()
    unique_records: list[dict] = []
    n_duplicates = 0

    for record in raw_records:
        lid = record.get("log_id")
        if lid in seen_ids:
            n_duplicates +=1
        else: 
            seen_ids.add(lid)
            unique_records.append(record)

    log.info(f"Duplicates Removed: {n_duplicates:,}")

    clean_records: list[dict] = []
    failed_records: list[dict] = []

    for record in unique_records:
        is_valid, reason = validate_record(record)
        if is_valid:
            clean_records.append(record)
        else:
            record["_fail_reason"] = reason
            failed_records.append(record)

    log.info(f"Clean Records: {len(clean_records):,}")
    log.info(f"Failed Records: {len(failed_records):,}")


    with open (failed_path, "w", encoding="utf-8") as f:
        for record in failed_records:
            f.write(json.dumps(record) + "\n")
    log.info(f"Failed Records Saived: {failed_path.name}")


    devices_map: dict[str, dict] = {}
    events: list[dict] = []
    errors: list[dict] = []

    for record in clean_records:
        did = record["device_id"]
        if did not in devices_map:
            devices_map[did] = extract_device(record)

        events.append(extract_event(record))

        error_row = extract_error(record)
        if error_row:
            errors.append(error_row)

    devices = list(devices_map.values())

#write csv
    write_csv(devices, processed_dir / "devices.csv")
    write_csv(events, processed_dir / "events.csv")
    write_csv(errors, processed_dir / "errors.csv")


#summary
    summary = {
        "total_read": len(raw_records),
        "duplicates": n_duplicates,
        "failed": len(failed_records),
        "clean": len(clean_records),
        "devices": len(devices),
        "events": len(events),
        "errors": len(errors),
    }

    log.info(f"===== ETL pipeline completed =====")
    for k, v in summary.items():
        log.info(f"{k:<16}, {v:,}")
    return summary 

if __name__ == "__main__":
    run_etl()

        


