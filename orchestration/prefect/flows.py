import argparse
import subprocess
from pathlib import Path

from prefect import flow, task

REPO_ROOT = Path(__file__).resolve().parents[2]

@task(retries=1, retry_delay_seconds=10)
def run_dlt() -> None:
    result = subprocess.run(
        ["uv", "run", "python", "dlt_pipeline.py"],
        cwd=REPO_ROOT / "src" / "dlt_pipeline",
        check=True,
        capture_output=True,
        text=True,
    )
    print(result.stdout)
    if result.stderr:
        print(result.stderr)

@task(retries=1, retry_delay_seconds=10)
def run_dbt() -> None:
    result = subprocess.run(
        ["uv", "run", "--group", "dbt-duckdb", "dbt", "build"],
        cwd=REPO_ROOT / "dbt",
        check=True,
        capture_output=True,
        text=True,
    )
    print(result.stdout)
    if result.stderr:
        print(result.stderr)

@flow(log_prints=True)
def elt_flow() -> None:
    run_dlt()
    run_dbt()
    print("ELT flow complete: bronze refreshed -> gold rebuilt + tests green")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Olist ELT flow (dlt -> dbt).")
    parser.add_argument("--serve", action="store_true",
                        help="Serve the flow as the scheduled 'elt-daily' deployment (daily 07:00).")
    args = parser.parse_args()

    if args.serve:
        elt_flow.serve(
            name="elt-daily",
            cron="0 7 * * *",
            limit=1,
            pause_on_shutdown=False,
        )
    else:
        elt_flow()