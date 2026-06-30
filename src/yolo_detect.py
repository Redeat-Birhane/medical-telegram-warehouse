import os
import csv
import logging
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# ─── Load .env ────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env", override=True)

# ─── Directories ──────────────────────────────────────────────────────────────
IMAGES_DIR  = BASE_DIR / "data" / "raw" / "images"
OUTPUT_DIR  = BASE_DIR / "data" / "processed"
LOGS_DIR    = BASE_DIR / "logs"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_CSV  = OUTPUT_DIR / "yolo_detections.csv"

# ─── Logging ──────────────────────────────────────────────────────────────────
log_file = LOGS_DIR / f"yolo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# ─── Confidence threshold ─────────────────────────────────────────────────────
CONFIDENCE_THRESHOLD = 0.3


# ─── Image category classifier ────────────────────────────────────────────────

def classify_image(detected_classes: list[str]) -> str:
    """
    Classify image based on detected object classes.

    promotional    — person + bottle/product detected
    product_display — bottle/container/product, no person
    lifestyle      — person only, no product
    other          — nothing relevant detected
    """
    person_labels = {"person"}
    product_labels = {
        "bottle", "cup", "bowl", "vase", "book",
        "box", "suitcase", "handbag", "backpack",
        "scissors", "toothbrush", "hair drier",
    }

    detected = set(detected_classes)
    has_person  = bool(detected & person_labels)
    has_product = bool(detected & product_labels)

    if has_person and has_product:
        return "promotional"
    elif has_product and not has_person:
        return "product_display"
    elif has_person and not has_product:
        return "lifestyle"
    else:
        return "other"


# ─── Discover images ──────────────────────────────────────────────────────────

def discover_images() -> list[tuple[str, int, Path]]:
    """
    Walk data/raw/images/{channel_name}/{message_id}.jpg
    Returns list of (channel_name, message_id, image_path).
    """
    images = []

    try:
        for channel_dir in sorted(IMAGES_DIR.iterdir()):
            if not channel_dir.is_dir():
                continue

            channel_name = channel_dir.name

            for img_path in sorted(channel_dir.glob("*.jpg")):
                try:
                    message_id = int(img_path.stem)
                    images.append((channel_name, message_id, img_path))
                except ValueError:
                    logger.warning(f"Skipping non-numeric filename: {img_path.name}")
                    continue

    except Exception as e:
        logger.error(f"Error discovering images: {e}")

    logger.info(f"Found {len(images)} images across {len(list(IMAGES_DIR.iterdir()))} channels")
    return images


# ─── Run YOLO detection ───────────────────────────────────────────────────────

def run_detection(images: list[tuple[str, int, Path]]) -> list[dict]:
    """
    Run YOLOv8 nano detection on each image.
    Returns list of detection result dicts.
    """
    try:
        from ultralytics import YOLO
        logger.info("Loading YOLOv8 nano model (yolov8n.pt)...")
        model = YOLO("yolov8n.pt")
        logger.info("Model loaded successfully.")
    except Exception as e:
        logger.critical(f"Failed to load YOLO model: {e}")
        return []

    results_data = []
    total = len(images)

    for idx, (channel_name, message_id, img_path) in enumerate(images, 1):
        try:
            logger.info(f"[{idx:>4}/{total}] Processing: {channel_name}/{img_path.name}")

            results = model(str(img_path), verbose=False)

            detected_classes    = []
            detected_confidence = []

            for result in results:
                if result.boxes is None:
                    continue

                for box in result.boxes:
                    try:
                        conf       = float(box.conf[0])
                        class_id   = int(box.cls[0])
                        class_name = model.names[class_id]

                        if conf >= CONFIDENCE_THRESHOLD:
                            detected_classes.append(class_name)
                            detected_confidence.append(round(conf, 4))
                    except Exception as box_err:
                        logger.warning(f"  Box parse error: {box_err}")
                        continue

            image_category = classify_image(detected_classes)
            avg_confidence = (
                round(sum(detected_confidence) / len(detected_confidence), 4)
                if detected_confidence else 0.0
            )

            record = {
                "message_id":       message_id,
                "channel_name":     channel_name,
                "image_path":       str(img_path),
                "detected_objects": ", ".join(detected_classes) if detected_classes else "none",
                "object_count":     len(detected_classes),
                "confidence_scores": ", ".join(str(c) for c in detected_confidence),
                "avg_confidence":   avg_confidence,
                "image_category":   image_category,
                "processed_at":     datetime.utcnow().isoformat(),
            }

            results_data.append(record)
            logger.info(
                f"       -> {image_category} | "
                f"objects: {detected_classes or 'none'} | "
                f"avg_conf: {avg_confidence}"
            )

        except Exception as img_err:
            logger.error(f"  Failed to process {img_path.name}: {img_err}")
            # Still record the failure so we know which images had issues
            results_data.append({
                "message_id":        message_id,
                "channel_name":      channel_name,
                "image_path":        str(img_path),
                "detected_objects":  "error",
                "object_count":      0,
                "confidence_scores": "",
                "avg_confidence":    0.0,
                "image_category":    "error",
                "processed_at":      datetime.utcnow().isoformat(),
            })
            continue

    return results_data


# ─── Save results ─────────────────────────────────────────────────────────────

def save_results(results: list[dict]) -> None:
    if not results:
        logger.warning("No results to save.")
        return

    fieldnames = [
        "message_id", "channel_name", "image_path",
        "detected_objects", "object_count", "confidence_scores",
        "avg_confidence", "image_category", "processed_at",
    ]

    try:
        with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)

        logger.info(f"Results saved to: {OUTPUT_CSV}")
    except Exception as e:
        logger.error(f"Failed to save CSV: {e}")


# ─── Summary ──────────────────────────────────────────────────────────────────

def print_summary(results: list[dict]) -> None:
    if not results:
        return

    categories = {}
    for r in results:
        cat = r["image_category"]
        categories[cat] = categories.get(cat, 0) + 1

    logger.info("")
    logger.info("=" * 44)
    logger.info("          YOLO DETECTION SUMMARY")
    logger.info("=" * 44)
    logger.info(f"  Total images processed : {len(results)}")
    logger.info("  Category breakdown:")
    for cat, count in sorted(categories.items()):
        pct = round(count / len(results) * 100, 1)
        logger.info(f"    {cat:<20} {count:>4} ({pct}%)")
    logger.info(f"  Output CSV : {OUTPUT_CSV}")
    logger.info("=" * 44)


# ─── Entry point ──────────────────────────────────────────────────────────────

def main():
    logger.info("=== YOLO Object Detection Started ===")
    logger.info(f"Images dir : {IMAGES_DIR}")
    logger.info(f"Confidence : >= {CONFIDENCE_THRESHOLD}")
    logger.info("")

    try:
        images = discover_images()

        if not images:
            logger.warning("No images found. Run scraper first.")
            return

        results = run_detection(images)
        save_results(results)
        print_summary(results)

    except Exception as e:
        logger.critical(f"Unexpected error: {e}")


if __name__ == "__main__":
    main()