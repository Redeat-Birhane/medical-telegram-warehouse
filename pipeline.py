import subprocess
import sys
from pathlib import Path

from dagster import (
    op, job, OpExecutionContext, Failure,
    ScheduleDefinition, DefaultScheduleStatus,
    In, Out, Nothing,
)

BASE_DIR = Path(__file__).resolve().parent
DBT_PROJECT_DIR = BASE_DIR / "medical_warehouse"


def run_subprocess(context: OpExecutionContext, cmd: list[str], cwd: Path, step_name: str):
    """
    Run a subprocess command, stream output to Dagster logs,
    and raise a Dagster Failure if it errors out.
    """
    context.log.info(f"Starting: {step_name}")
    context.log.info(f"Command: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=3600,
        )

        if result.stdout:
            context.log.info(result.stdout)
        if result.stderr:
            context.log.warning(result.stderr)

        if result.returncode != 0:
            raise Failure(
                description=f"{step_name} failed with exit code {result.returncode}",
                metadata={"stderr": result.stderr[-2000:] if result.stderr else "N/A"},
            )

        context.log.info(f"Completed: {step_name}")

    except subprocess.TimeoutExpired:
        raise Failure(description=f"{step_name} timed out after 1 hour")
    except Failure:
        raise
    except Exception as e:
        raise Failure(description=f"{step_name} raised an unexpected error: {e}")


# ─── Op 1: Scrape Telegram ──────────────────────────────────────────────────────

@op(out=Out(Nothing), description="Scrape messages and images from configured Telegram channels")
def scrape_telegram_data(context: OpExecutionContext):
    run_subprocess(
        context,
        [sys.executable, "src/scraper.py"],
        cwd=BASE_DIR,
        step_name="Telegram scraping",
    )


# ─── Op 2: Load raw data to Postgres ────────────────────────────────────────────

@op(
    ins={"start": In(Nothing)},
    out=Out(Nothing),
    description="Load raw JSON data lake files into PostgreSQL raw schema",
)
def load_raw_to_postgres(context: OpExecutionContext):
    run_subprocess(
        context,
        [sys.executable, "src/load_raw.py"],
        cwd=BASE_DIR,
        step_name="Load raw data to PostgreSQL",
    )


# ─── Op 3: Run dbt transformations ──────────────────────────────────────────────

@op(
    ins={"start": In(Nothing)},
    out=Out(Nothing),
    description="Run dbt staging and mart models, then run dbt tests",
)
def run_dbt_transformations(context: OpExecutionContext):
    run_subprocess(
        context,
        ["dbt", "run"],
        cwd=DBT_PROJECT_DIR,
        step_name="dbt run",
    )
    run_subprocess(
        context,
        ["dbt", "test"],
        cwd=DBT_PROJECT_DIR,
        step_name="dbt test",
    )


# ─── Op 4: Run YOLO enrichment ──────────────────────────────────────────────────

@op(
    ins={"start": In(Nothing)},
    out=Out(Nothing),
    description="Run YOLOv8 object detection on downloaded images",
)
def run_yolo_enrichment(context: OpExecutionContext):
    run_subprocess(
        context,
        [sys.executable, "src/yolo_detect.py"],
        cwd=BASE_DIR,
        step_name="YOLO object detection",
    )


# ─── Op 5: Load YOLO results and re-run dbt for image marts ────────────────────

@op(
    ins={"start": In(Nothing)},
    out=Out(Nothing),
    description="Load YOLO results into Postgres and rebuild fct_image_detections",
)
def load_yolo_and_rebuild_marts(context: OpExecutionContext):
    run_subprocess(
        context,
        [sys.executable, "src/load_yolo_results.py"],
        cwd=BASE_DIR,
        step_name="Load YOLO results to PostgreSQL",
    )
    run_subprocess(
        context,
        ["dbt", "run", "--select", "stg_yolo_detections", "fct_image_detections"],
        cwd=DBT_PROJECT_DIR,
        step_name="Rebuild image detection marts",
    )
    run_subprocess(
        context,
        ["dbt", "test"],
        cwd=DBT_PROJECT_DIR,
        step_name="dbt test (post-YOLO)",
    )


# ─── Job: wire up the dependency graph ──────────────────────────────────────────

@job(
    description=(
        "Full medical Telegram data pipeline: "
        "scrape -> load raw -> dbt transform -> YOLO enrich -> load YOLO -> rebuild marts"
    )
)
def medical_warehouse_pipeline():
    scraped = scrape_telegram_data()
    loaded = load_raw_to_postgres(start=scraped)
    transformed = run_dbt_transformations(start=loaded)
    detected = run_yolo_enrichment(start=transformed)
    load_yolo_and_rebuild_marts(start=detected)


# ─── Schedule: run daily at 2 AM ────────────────────────────────────────────────

daily_schedule = ScheduleDefinition(
    job=medical_warehouse_pipeline,
    cron_schedule="0 2 * * *",   # 2:00 AM every day
    default_status=DefaultScheduleStatus.STOPPED,  # start paused; enable manually in UI
    description="Runs the full pipeline daily at 2 AM",
)