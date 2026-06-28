import os
import json
import logging
from datetime import datetime
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

# ─── Load .env from project root ──────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env", override=True)

# ─── Config ───────────────────────────────────────────────────────────────────
DB_CONFIG = {
    "host":     os.getenv("POSTGRES_HOST", "localhost"),
    "port":     int(os.getenv("POSTGRES_PORT", 5432)),
    "dbname":   os.getenv("POSTGRES_DB", "medical_warehouse"),
    "user":     os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD"),
}

DATA_RAW_DIR = BASE_DIR / "data" / "raw" / "telegram_messages"
LOGS_DIR     = BASE_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# ─── Logging ──────────────────────────────────────────────────────────────────
log_file = LOGS_DIR / f"load_raw_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

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
        logger.info(
            f"Connected to PostgreSQL: "
            f"{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['dbname']}"
        )
        return conn
    except Exception as e:
        logger.critical(f"Could not connect to PostgreSQL: {e}")
        raise


def create_schema_and_table(conn):
    ddl = """
        CREATE SCHEMA IF NOT EXISTS raw;

        CREATE TABLE IF NOT EXISTS raw.telegram_messages (
            id               SERIAL PRIMARY KEY,
            message_id       BIGINT        NOT NULL,
            channel_name     VARCHAR(255)  NOT NULL,
            channel_title    VARCHAR(255),
            message_date     TIMESTAMPTZ,
            message_text     TEXT,
            has_media        BOOLEAN       DEFAULT FALSE,
            image_path       TEXT,
            views            INTEGER       DEFAULT 0,
            forwards         INTEGER       DEFAULT 0,
            scraped_at       TIMESTAMPTZ,
            loaded_at        TIMESTAMPTZ   DEFAULT NOW(),

            CONSTRAINT uq_message UNIQUE (message_id, channel_name)
        );
    """
    try:
        with conn.cursor() as cur:
            cur.execute(ddl)
        conn.commit()
        logger.info("Schema 'raw' and table 'raw.telegram_messages' are ready.")
    except Exception as e:
        conn.rollback()
        logger.error(f"Failed to create schema/table: {e}")
        raise


# ─── JSON discovery ───────────────────────────────────────────────────────────

def discover_json_files() -> list[Path]:
    json_files = sorted(DATA_RAW_DIR.rglob("*.json"))

    if not json_files:
        logger.warning(f"No JSON files found under: {DATA_RAW_DIR}")
    else:
        logger.info(f"Found {len(json_files)} JSON file(s):")
        for f in json_files:
            logger.info(f"  {f.relative_to(BASE_DIR)}")

    return json_files


# ─── Load a single JSON file ──────────────────────────────────────────────────

def load_json_file(conn, json_path: Path) -> tuple[int, int]:
    inserted = 0
    skipped  = 0

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            records = json.load(f)
    except Exception as e:
        logger.error(f"Could not read {json_path}: {e}")
        return 0, 0

    if not records:
        logger.warning(f"  {json_path.name} is empty — skipping.")
        return 0, 0

    logger.info(f"  Loading {json_path.name}: {len(records)} records...")

    rows = []
    for r in records:
        try:
            rows.append((
                r.get("message_id"),
                r.get("channel_name", ""),
                r.get("channel_title", ""),
                r.get("message_date"),
                r.get("message_text", ""),
                bool(r.get("has_media", False)),
                r.get("image_path"),
                int(r.get("views", 0) or 0),
                int(r.get("forwards", 0) or 0),
                r.get("scraped_at"),
            ))
        except Exception as row_err:
            logger.warning(
                f"    Skipping malformed record "
                f"{r.get('message_id', '?')}: {row_err}"
            )
            skipped += 1
            continue

    if not rows:
        logger.warning(f"  No valid rows from {json_path.name}.")
        return 0, skipped

    insert_sql = """
        INSERT INTO raw.telegram_messages (
            message_id, channel_name, channel_title,
            message_date, message_text, has_media,
            image_path, views, forwards, scraped_at
        )
        VALUES %s
        ON CONFLICT (message_id, channel_name) DO NOTHING;
    """

    try:
        with conn.cursor() as cur:
            execute_values(cur, insert_sql, rows)
            inserted = cur.rowcount
        conn.commit()
        duplicates = len(rows) - inserted
        logger.info(f"    Inserted: {inserted} | Duplicates skipped: {duplicates}")
        skipped += duplicates
    except Exception as db_err:
        conn.rollback()
        logger.error(f"    DB insert failed for {json_path.name}: {db_err}")

    return inserted, skipped


# ─── Entry point ──────────────────────────────────────────────────────────────

def main():
    logger.info("=== Raw Data Loader Started ===")
    logger.info(f"Source : {DATA_RAW_DIR}")
    logger.info(
        f"Target : {DB_CONFIG['host']}:{DB_CONFIG['port']}"
        f"/{DB_CONFIG['dbname']}"
    )
    logger.info("")

    try:
        conn = get_connection()
    except Exception:
        logger.critical("Aborting — cannot connect to database.")
        return

    try:
        create_schema_and_table(conn)
    except Exception:
        logger.critical("Aborting — could not create schema/table.")
        conn.close()
        return

    json_files     = discover_json_files()
    total_inserted = 0
    total_skipped  = 0

    for json_path in json_files:
        try:
            ins, skip       = load_json_file(conn, json_path)
            total_inserted += ins
            total_skipped  += skip
        except Exception as e:
            logger.error(f"Unexpected error loading {json_path.name}: {e}")
            continue

    logger.info("")
    logger.info("=" * 44)
    logger.info("              LOAD SUMMARY")
    logger.info("=" * 44)
    logger.info(f"  Files processed : {len(json_files)}")
    logger.info(f"  Rows inserted   : {total_inserted}")
    logger.info(f"  Rows skipped    : {total_skipped}")
    logger.info("=" * 44)

    conn.close()
    logger.info("Done.")


if __name__ == "__main__":
    main()