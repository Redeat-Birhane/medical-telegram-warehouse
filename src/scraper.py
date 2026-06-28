import os
import json
import asyncio
import logging
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.types import MessageMediaPhoto

# ─── Load .env from project root ──────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env", override=True)

# ─── Validate credentials ─────────────────────────────────────────────────────
_api_id_raw = os.getenv("TELEGRAM_API_ID")
_api_hash   = os.getenv("TELEGRAM_API_HASH")
_phone      = os.getenv("TELEGRAM_PHONE")

if not _api_id_raw or not _api_hash or not _phone:
    raise EnvironmentError(
        "\n[ERROR] Missing Telegram credentials in .env file.\n"
        f"  Looked for .env at: {BASE_DIR / '.env'}\n"
        "  Make sure these three keys are set:\n"
        "    TELEGRAM_API_ID=...\n"
        "    TELEGRAM_API_HASH=...\n"
        "    TELEGRAM_PHONE=...\n"
    )

try:
    API_ID = int(_api_id_raw)
except ValueError:
    raise EnvironmentError(
        f"[ERROR] TELEGRAM_API_ID must be a number, got: '{_api_id_raw}'"
    )

API_HASH = _api_hash
PHONE    = _phone

# ─── Channels ─────────────────────────────────────────────────────────────────
CHANNELS = [
    "CheMed123",
    "lobelia4cosmetics",
    "tikvahpharma",
]

MESSAGE_LIMIT  = 200    
MAX_IMAGES     = 50    
DOWNLOAD_IMAGES = True  
# ─────────────────────────────────────────────────────────────────────────────

# ─── Directories ──────────────────────────────────────────────────────────────
DATA_RAW_DIR = BASE_DIR / "data" / "raw"
MESSAGES_DIR = DATA_RAW_DIR / "telegram_messages"
IMAGES_DIR   = DATA_RAW_DIR / "images"
LOGS_DIR     = BASE_DIR / "logs"

for d in [MESSAGES_DIR, IMAGES_DIR, LOGS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ─── Logging ──────────────────────────────────────────────────────────────────
log_file = LOGS_DIR / f"scraper_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(),
    ],
)

for handler in logging.root.handlers:
    if isinstance(handler, logging.FileHandler):
        handler.stream = open(handler.baseFilename, "a", encoding="utf-8")


logging.getLogger("telethon").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def get_message_date_str() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")


def get_messages_output_path(channel_name: str, date_str: str) -> Path:
    partition_dir = MESSAGES_DIR / date_str
    partition_dir.mkdir(parents=True, exist_ok=True)
    return partition_dir / f"{channel_name}.json"


def get_image_output_path(channel_name: str, message_id: int) -> Path:
    channel_dir = IMAGES_DIR / channel_name
    channel_dir.mkdir(parents=True, exist_ok=True)
    return channel_dir / f"{message_id}.jpg"


# ─── Core scraping logic ──────────────────────────────────────────────────────

async def scrape_channel(client: TelegramClient, channel_username: str) -> list[dict]:
    """
    Scrape up to MESSAGE_LIMIT messages from a channel.
    Downloads up to MAX_IMAGES images.
    """
    messages_data = []
    date_str      = get_message_date_str()
    image_count   = 0

    try:
        logger.info(f"┌─ Scraping @{channel_username}")
        logger.info(f"│  Message limit : {MESSAGE_LIMIT or 'unlimited'}")
        logger.info(f"│  Image limit   : {MAX_IMAGES or 'unlimited'} | enabled={DOWNLOAD_IMAGES}")

        entity = await client.get_entity(channel_username)
        channel_name  = getattr(entity, "username", None) or channel_username
        channel_title = getattr(entity, "title", channel_username)

        logger.info(f"│  Resolved      : '{channel_title}' (@{channel_name})")

        async for message in client.iter_messages(entity, limit=MESSAGE_LIMIT):
            try:
                has_media  = False
                image_path = None

                # ── Download image (if within limits) ─────────────────────
                if (
                    DOWNLOAD_IMAGES
                    and message.media
                    and isinstance(message.media, MessageMediaPhoto)
                ):
                    has_media = True

                    if MAX_IMAGES is None or image_count < MAX_IMAGES:
                        img_path = get_image_output_path(channel_name, message.id)

                        try:
                            await client.download_media(message.media, file=str(img_path))
                            image_path  = str(img_path)
                            image_count += 1
                            logger.info(f"│  [{image_count:>3}] Image saved: {img_path.name}")
                        except Exception as img_err:
                            logger.warning(f"│  Image download failed (msg {message.id}): {img_err}")
                    else:
                        
                        logger.info(f"│  Image limit reached ({MAX_IMAGES}), skipping downloads.")

                # ── Record ─────────────────────────────────────────────────
                record = {
                    "message_id":    message.id,
                    "channel_name":  channel_name,
                    "channel_title": channel_title,
                    "message_date":  message.date.isoformat() if message.date else None,
                    "message_text":  message.text or "",
                    "has_media":     has_media,
                    "image_path":    image_path,
                    "views":         message.views or 0,
                    "forwards":      message.forwards or 0,
                    "scraped_at":    datetime.utcnow().isoformat(),
                }

                messages_data.append(record)

            except Exception as msg_err:
                logger.error(f"│  Error on msg {getattr(message, 'id', '?')}: {msg_err}")
                continue

        # ── Save to data lake ──────────────────────────────────────────────
        output_path = get_messages_output_path(channel_name, date_str)

        existing = []
        if output_path.exists():
            try:
                with open(output_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                existing = []

        existing_ids = {r["message_id"] for r in existing}
        new_records  = [r for r in messages_data if r["message_id"] not in existing_ids]
        all_records  = existing + new_records

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(all_records, f, ensure_ascii=False, indent=2)

        logger.info(f"└─ Done: {len(new_records)} new messages, {image_count} images → {output_path.name}")

    except Exception as channel_err:
        logger.error(f"└─ Failed @{channel_username}: {channel_err}")

    return messages_data


# ─── Summary ──────────────────────────────────────────────────────────────────

def print_summary(results: dict[str, int]) -> None:
    total = 0
    logger.info("")
    logger.info("=" * 44)
    logger.info("              SCRAPING SUMMARY")
    logger.info("=" * 44)
    for channel, count in results.items():
        logger.info(f"  @{channel:<25} {count:>5} messages")
        total += count
    logger.info("-" * 44)
    logger.info(f"  {'TOTAL':<25} {total:>5} messages")
    logger.info("=" * 44)


# ─── Entry point ──────────────────────────────────────────────────────────────

async def main():
    logger.info("=== Telegram Medical Channel Scraper ===")
    logger.info(f"Channels : {', '.join('@' + c for c in CHANNELS)}")
    logger.info(f"Msg limit: {MESSAGE_LIMIT or 'unlimited'} | "
                f"Img limit: {MAX_IMAGES or 'unlimited'} | "
                f"Download : {DOWNLOAD_IMAGES}")
    logger.info("")

    results = {}

    try:
        async with TelegramClient("telegram_session", API_ID, API_HASH) as client:
            try:
                await client.start(phone=PHONE)
                logger.info("Authenticated successfully.\n")
            except Exception as auth_err:
                logger.critical(f"Authentication failed: {auth_err}")
                return

            for channel in CHANNELS:
                try:
                    messages       = await scrape_channel(client, channel)
                    results[channel] = len(messages)
                except Exception as ch_err:
                    logger.error(f"Skipping @{channel}: {ch_err}")
                    results[channel] = 0

    except Exception as client_err:
        logger.critical(f"Client error: {client_err}")
        return

    print_summary(results)


if __name__ == "__main__":
    asyncio.run(main())