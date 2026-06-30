import os
import csv
import logging
from datetime import datetime
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

# ─── Load .env ────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env", override=True)

DB_CONFIG = {
    "host":     os.getenv("POSTGRES_HOST", "localhost"),
    "port":     int(os.getenv("POSTGRES_PORT", 5432)),
    "dbname":   os.getenv("POSTGRES_DB", "medical_warehouse"),
    "user":     os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD"),
}

CSV_PATH = BASE_DIR / "data" / "processed" / "yolo_detections.csv"
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# ─── Logging ──────────────────────────────────────────────────────────────────
log_file = LOGS_DIR / f"load_yolo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


# ─── Database helpers ─────────────────────────────────────────────────────────

def get_connection():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        logger.info(f"Connected to PostgreSQL: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['dbname']}")
        return conn
    except Exception as e:
        logger.critical(f"Could not connect to PostgreSQL: {e}")
        raise


def create_table(conn):
    ddl = """
        CREATE SCHEMA IF NOT EXISTS raw;

        CREATE TABLE IF NOT EXISTS raw.yolo_detections (
            id                  SERIAL PRIMARY KEY,
            message_id          BIGINT        NOT NULL,
            channel_name        VARCHAR(255)  NOT NULL,
            image_path          TEXT,
            detected_objects    TEXT,
            object_count        INTEGER       DEFAULT 0,
            confidence_scores   TEXT,
            avg_confidence      NUMERIC(5,4)  DEFAULT 0,
            image_category      VARCHAR(50),
            processed_at        TIMESTAMPTZ,
            loaded_at           TIMESTAMPTZ   DEFAULT NOW(),

            CONSTRAINT uq_yolo_message UNIQUE (message_id, channel_name)
        );
    """
    try:
        with conn.cursor() as cur:
            cur.execute(ddl)
        conn.commit()
        logger.info("Table 'raw.yolo_detections' is ready.")
    except Exception as e:
        conn.rollback()
        logger.error(f"Failed to create table: {e}")
        raise


def load_csv(conn) -> tuple[int, int]:
    if not CSV_PATH.exists():
        logger.critical(f"CSV file not found: {CSV_PATH}")
        return 0, 0

    rows = []
    skipped = 0

    with open(CSV_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            try:
                rows.append((
                    int(r["message_id"]),
                    r["channel_name"],
                    r["image_path"],
                    r["detected_objects"],
                    int(r["object_count"] or 0),
                    r["confidence_scores"],
                    float(r["avg_confidence"] or 0),
                    r["image_category"],
                    r["processed_at"],
                ))
            except Exception as row_err:
                logger.warning(f"  Skipping malformed row {r.get('message_id', '?')}: {row_err}")
                skipped += 1
                continue

    if not rows:
        logger.warning("No valid rows found in CSV.")
        return 0, skipped

    insert_sql = """
        INSERT INTO raw.yolo_detections (
            message_id, channel_name, image_path,
            detected_objects, object_count, confidence_scores,
            avg_confidence, image_category, processed_at
        )
        VALUES %s
        ON CONFLICT (message_id, channel_name)
        DO UPDATE SET
            detected_objects   = EXCLUDED.detected_objects,
            object_count       = EXCLUDED.object_count,
            confidence_scores  = EXCLUDED.confidence_scores,
            avg_confidence     = EXCLUDED.avg_confidence,
            image_category     = EXCLUDED.image_category,
            processed_at       = EXCLUDED.processed_at,
            loaded_at          = NOW();
    """

    try:
        with conn.cursor() as cur:
            execute_values(cur, insert_sql, rows)
        conn.commit()
        logger.info(f"Inserted/updated {len(rows)} rows from YOLO results CSV.")
    except Exception as db_err:
        conn.rollback()
        logger.error(f"DB insert failed: {db_err}")
        return 0, len(rows)

    return len(rows), skipped


def main():
    logger.info("=== YOLO Results Loader Started ===")
    logger.info(f"Source : {CSV_PATH}")

    try:
        conn = get_connection()
    except Exception:
        logger.critical("Aborting — cannot connect to database.")
        return

    try:
        create_table(conn)
    except Exception:
        logger.critical("Aborting — could not create table.")
        conn.close()
        return

    inserted, skipped = load_csv(conn)

    logger.info("")
    logger.info("=" * 44)
    logger.info("           YOLO LOAD SUMMARY")
    logger.info("=" * 44)
    logger.info(f"  Rows loaded  : {inserted}")
    logger.info(f"  Rows skipped : {skipped}")
    logger.info("=" * 44)

    conn.close()
    logger.info("Done.")


if __name__ == "__main__":
    main()