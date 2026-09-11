import argparse
import subprocess
from pathlib import Path

from prefect import flow, task

REPO_ROOT = Path(__file__).resolve().parents[2]

@task(retries=1, retry_delay_seconds=10)
def run_elt() -> None:
    result = subprocess.run(
        ["uv", "run", "elt"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    print(result.stdout)
    if result.stderr:
        print(result.stderr)

@flow(log_prints=True)
def elt_flow() -> None:
    run_elt()
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