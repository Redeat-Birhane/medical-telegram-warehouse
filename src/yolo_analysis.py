import os
import logging
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env", override=True)

DB_CONFIG = {
    "host":     os.getenv("POSTGRES_HOST", "localhost"),
    "port":     int(os.getenv("POSTGRES_PORT", 5432)),
    "dbname":   os.getenv("POSTGRES_DB", "medical_warehouse"),
    "user":     os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD"),
}

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def run_query(conn, title: str, sql: str):
    logger.info("")
    logger.info("=" * 60)
    logger.info(title)
    logger.info("=" * 60)
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            columns = [desc[0] for desc in cur.description]
            rows = cur.fetchall()

            logger.info(" | ".join(f"{c:<25}" for c in columns))
            logger.info("-" * 60)
            for row in rows:
                logger.info(" | ".join(f"{str(v):<25}" for v in row))
    except Exception as e:
        logger.error(f"Query failed: {e}")


def main():
    conn = psycopg2.connect(**DB_CONFIG)

    # ── Q1: Do promotional posts get more views than product_display? ────────
    run_query(conn, "Q1: Avg views by image category", """
        select
            image_category,
            count(*)                          as image_count,
            round(avg(view_count), 1)         as avg_views,
            round(avg(forward_count), 1)      as avg_forwards
        from staging_marts.fct_image_detections
        group by image_category
        order by avg_views desc;
    """)

    # ── Q2: Which channels use the most visual content? ──────────────────────
    run_query(conn, "Q2: Visual content usage by channel", """
        select
            c.channel_name,
            c.total_posts,
            count(d.message_id)                                   as images_detected,
            round(100.0 * count(d.message_id) / c.total_posts, 1)  as pct_with_image
        from staging_marts.dim_channels c
        left join staging_marts.fct_image_detections d
            on c.channel_name = d.channel_name
        group by c.channel_name, c.total_posts
        order by pct_with_image desc;
    """)

    # ── Q3: Image category distribution per channel ──────────────────────────
    run_query(conn, "Q3: Image category breakdown per channel", """
        select
            channel_name,
            image_category,
            count(*) as count
        from staging_marts.fct_image_detections
        group by channel_name, image_category
        order by channel_name, count desc;
    """)

    # ── Q4: Top 10 most frequently mentioned products/drugs ──────────────────
    run_query(conn, "Q4: Top 10 most frequent words in message text (proxy for products)", """
        with words as (
            select
                lower(unnest(string_to_array(
                    regexp_replace(message_text, '[^a-zA-Z\\s]', '', 'g'),
                    ' '
                ))) as word
            from staging_marts.fct_messages
            where message_text is not null
        )
        select word, count(*) as mentions
        from words
        where length(word) > 4
        group by word
        order by mentions desc
        limit 10;
    """)

    conn.close()


if __name__ == "__main__":
    main()