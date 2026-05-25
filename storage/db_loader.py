import csv
import logging
import os
from pathlib import Path
import psycopg
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(Path(__file__).parents[1] / "logs" / "db_loader.log"),
    ],
)
log = logging.getLogger(__name__)

PROCESSED = Path(__file__).parents[1] / "data" / "processed"

#connection
def get_connection():
    return psycopg.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT")),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        sslmode="disable",
    )

#schema
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS devices (
    device_id   VARCHAR(20)  PRIMARY KEY,
    device_type VARCHAR(50)  NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    log_id      UUID         PRIMARY KEY,
    timestamp   TIMESTAMP    NOT NULL,
    device_id   VARCHAR(20)  REFERENCES devices(device_id),
    event_type  VARCHAR(10)  NOT NULL,
    message     TEXT,
    duration_ms INTEGER,
    status      VARCHAR(10),
    session_id  UUID,
    firmware    VARCHAR(20)
);

CREATE TABLE IF NOT EXISTS errors (
    log_id      UUID         PRIMARY KEY,
    timestamp   TIMESTAMP    NOT NULL,
    device_id   VARCHAR(20)  REFERENCES devices(device_id),
    event_type  VARCHAR(10)  NOT NULL,
    error_code  VARCHAR(10)  NOT NULL,
    message     TEXT,
    duration_ms INTEGER
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id  UUID         PRIMARY KEY,
    device_id   VARCHAR(20)  REFERENCES devices(device_id),
    firmware    VARCHAR(20),
    first_seen  TIMESTAMP,
    last_seen   TIMESTAMP,
    event_count INTEGER
);

CREATE INDEX IF NOT EXISTS idx_sessions_device_id ON sessions(device_id);
CREATE INDEX IF NOT EXISTS idx_events_timestamp  ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_device_id  ON events(device_id);
CREATE INDEX IF NOT EXISTS idx_events_event_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_errors_error_code ON errors(error_code);
CREATE INDEX IF NOT EXISTS idx_errors_device_id  ON errors(device_id);
"""

def create_schema(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL)
    conn.commit()
    log.info("Database schema created / verified.")


#loaders
def _read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))
    
def load_devices(conn, rows: list[dict]) ->int:
    sql = """
        INSERT INTO devices(device_id, device_type)
        VALUES (%s, %s)
        ON CONFLICT (device_id) DO NOTHING
        """
    with conn.cursor() as cur:
        cur.executemany(sql, [(r["device_id"], r["device_type"]) for r in rows])
    conn.commit()
    return len(rows)

def load_events(conn, rows: list[dict]) -> int:
    sql = """
        INSERT INTO events (log_id, timestamp, device_id, event_type, message, duration_ms, status, session_id, firmware)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (log_id) DO NOTHING
        """
    
    data = [
        (
            r["log_id"],
            r["timestamp"],
            r["device_id"],
            r["event_type"],
            r.get("message"),
            int(r["duration_ms"]) if r.get("duration_ms") else None,
            r.get("status"),
            r.get("session_id") or None,
            r.get("firmware"),
        )
        for r in rows
    ]
    with conn.cursor() as cur:
        cur.executemany(sql, data)
    conn.commit()
    return len(rows)

def load_errors(conn, rows: list[dict]) -> int:
    sql = """
        INSERT INTO errors (log_id, timestamp, device_id, event_type, error_code, message, duration_ms)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (log_id) DO NOTHING
        """
    
    data = [
        (
            r["log_id"],
            r["timestamp"],
            r["device_id"],
            r["event_type"],
            r.get("error_code"),
            r.get("message"),
            int(r["duration_ms"]) if r.get("duration_ms") else None,
        )
        for r in rows
    ]
    with conn.cursor() as cur:
        cur.executemany(sql, data)
    conn.commit()
    return len(rows)

def load_sessions(conn, rows: list[dict]) -> int:
    sql = """
        INSERT INTO sessions
            (session_id, device_id, firmware, first_seen, last_seen, event_count)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (session_id) DO NOTHING
    """
    from collections import defaultdict
    sessions: dict = defaultdict(lambda: {
        "device_id": None, "firmware": None,
        "first_seen": None, "last_seen": None, "event_count": 0
    })
    for r in rows:
        sid = r.get("session_id")
        if not sid:
            continue
        s = sessions[sid]
        s["device_id"] = r["device_id"]
        s["firmware"] = r.get("firmware")
        s["event_count"] += 1
        ts = r["timestamp"]
        if s["first_seen"] is None or ts < s["first_seen"]:
            s["first_seen"] = ts
        if s["last_seen"] is None or ts > s["last_seen"]:
            s["last_seen"] = ts

    data = [
        (sid, s["device_id"], s["firmware"],
         s["first_seen"], s["last_seen"], s["event_count"])
        for sid, s in sessions.items()
    ]
    with conn.cursor() as cur:
        cur.executemany(sql, data)
    conn.commit()
    return len(data)

#main
def run_loader(processed_dir: Path = PROCESSED) -> dict:
    log.info("===== DB Loader started =====")

    conn = get_connection()
    log.info("Database connection established.")

    create_schema(conn)

    devices_rows = _read_csv(processed_dir / "devices.csv")
    events_rows = _read_csv(processed_dir / "events.csv")
    errors_rows = _read_csv(processed_dir / "errors.csv")

    n_devices = load_devices(conn, devices_rows)
    log.info(f"Loaded {n_devices:,} devices.")

    n_events = load_events(conn, events_rows)
    log.info(f"Loaded {n_events:,} events.")

    n_errors = load_errors(conn, errors_rows)
    log.info(f"Loaded {n_errors:,} errors.")

    n_sessions = load_sessions(conn, events_rows)
    log.info(f"Loaded {n_sessions:,} sessions.")

    conn.close()

    summary = {
        "devices": n_devices,
        "events": n_events,
        "errors": n_errors,
        "sessions": n_sessions,
    }

    log.info(f"===== DB Loader completed =====")
    return summary 

if __name__ == "__main__":
    run_loader()