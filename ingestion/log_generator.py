import json
import random
import uuid
from datetime import datetime, timedelta
from pathlib import Path

DEVICE_TYPES = [
    "coronary_stent_monitor",
    "cardiac_catheter",
    "electrophysiology_recorder",
    "neurovascular_probe",
    "endoscopy_unit",
    "urology_sensor",
    "oncology_infusion_pump",
    "peripheral_vascular_monitor",
]

DEVICE_POOL = [
    {"device_id": f"DEV-{str(i).zfill(4)}", "device_type": random.choice(DEVICE_TYPES)}
    for i in range(1, 51)
]

FAULTY_DEVICES = {"DEV-0007", "DEV-0019", "DEV-0033"}

INFO_MESSAGES = [
    "Device initialized successfully",
    "Firmware version check passed",
    "Sensor calibration complete",
    "Patient session started",
    "Data transmission to central hub OK",
    "Battery level nominal",
    "Self-test passed",
    "Connection to gateway established",
]

WARNING_MESSAGES = [
    "Battery level below 20%",
    "Signal quality degraded",
    "Sensor drift detected — recalibration recommended",
    "High latency on data transmission",
    "Temperature outside optimal range",
    "Memory usage above 80%",
    "Partial packet loss on last upload",
]

ERROR_MESSAGES = [
    "Sensor failure — no signal",
    "Critical: data transmission timeout",
    "Hardware fault detected",
    "Firmware checksum mismatch",
    "Out of memory — buffer overflow",
    "Connection lost to central hub",
    "Calibration failed after 3 attempts",
    "Emergency shutdown triggered",
]

ERROR_CODES = {
    "info":    [None],
    "warning": ["W001", "W002", "W003", "W004"],
    "error":   ["E101", "E102", "E201", "E202", "E301", "E302", "E501"],
}

def _event_type_for_device(device_id: str) -> str:
    if device_id in FAULTY_DEVICES:
        return random.choices(
            ["info", "warning", "error"],
            weights=[20, 30, 50],
        )[0]
    return random.choices(
        ["info", "warning", "error"],
        weights=[70, 20, 10],
    )[0]

def _build_payload(event_type: str, duration_ms: int) -> dict:
    code = random.choice(ERROR_CODES[event_type])
    payload = {
        "duration_ms": duration_ms,
        "status": "ok" if event_type == "info" else (
                  "degraded" if event_type == "warning" else "failed"),
        "session_id": str(uuid.uuid4()),
        "firmware": f"v{random.randint(1, 3)}.{random.randint(0, 9)}.{random.randint(0, 9)}",
    }
    if code:
        payload["error_code"] = code
    return payload

def generate_log_entry(device: dict, timestamp: datetime) -> dict:
    event_type = _event_type_for_device(device["device_id"])
    duration_ms = random.randint(10, 5000)

    messages = {
        "info":    INFO_MESSAGES,
        "warning": WARNING_MESSAGES,
        "error":   ERROR_MESSAGES,
    }

    return {
        "log_id":      str(uuid.uuid4()),
        "timestamp":   timestamp.isoformat(),
        "device_id":   device["device_id"],
        "device_type": device["device_type"],
        "event_type":  event_type,
        "message":     random.choice(messages[event_type]),
        "payload":     _build_payload(event_type, duration_ms),
    }

def _inject_duplicate(entry: dict) -> dict:
    return dict(entry)

def _inject_missing_fields(entry: dict) -> dict:
    entry = dict(entry)
    droppable = ["device_type", "message", "payload"]
    for field in random.sample(droppable, k=random.randint(1, 2)):
        entry.pop(field, None)
    return entry

def _inject_invalid_record(entry: dict) -> dict:
    entry = dict(entry)
    corruption = random.choice(["bad_timestamp", "bad_event_type", "null_device"])
    if corruption == "bad_timestamp":
        entry["timestamp"] = "NOT_A_DATE"
    elif corruption == "bad_event_type":
        entry["event_type"] = "UNKNOWN"
    elif corruption == "null_device":
        entry["device_id"] = None
    return entry


def generate_logs(
        n_records: int = 10000,
        start_time: datetime | None = None,
        span_hours: int = 24,
        output_path: str | Path | None = None,
) -> list[dict]:
    if start_time is None:
        start_time = datetime.now() - timedelta(hours=span_hours)

    span_seconds = span_hours * 3600
    logs: list[dict] = []

    for _ in range(n_records):
        device = random.choice(DEVICE_POOL)
        offset = random.uniform(0, span_seconds)
        timestamp = start_time + timedelta(seconds=offset)
        logs.append(generate_log_entry(device, timestamp))

    total = len(logs)
    issues = []

    n_dup = int(total * 0.05)
    issues.extend([_inject_duplicate(e) for e in random.sample(logs, n_dup)])

    n_miss = int(total * 0.03)
    issues.extend([_inject_missing_fields(e) for e in random.sample(logs, n_miss)])

    n_inv = int(total * 0.02)
    issues.extend([_inject_invalid_record(e) for e in random.sample(logs, n_inv)])

    logs.extend(issues)
    random.shuffle(logs)

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            for entry in logs:
                f.write(json.dumps(entry) + "\n")
        print(f"[generator] wrote {len(logs):,} records -> {output_path}")

    return logs


if __name__ == "__main__":
    out = Path(__file__).parents[1] / "data" / "raw" / "device_logs.jsonl"
    logs = generate_logs(n_records=10000, output_path=out)
    print(f"[generator] total records (incl. issues): {len(logs):,}")

    from collections import Counter
    types = Counter(e.get("event_type", "MISSING") for e in logs)
    print("[generator] event_type distribution:", dict(types))