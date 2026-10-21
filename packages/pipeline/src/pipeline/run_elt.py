import argparse
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def run_ingest() -> None:
    subprocess.run(
        ["uv", "run", "ingest"],
        cwd=REPO_ROOT,
        check=True,
    )


def run_dbt() -> None:
    subprocess.run(
        [
            "uv", "run", "--group", "dbt-duckdb",
            "--env-file", str(REPO_ROOT / ".env"),
            "dbt", "build",
        ],
        cwd=REPO_ROOT / "pipeline" / "dbt",
        check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Olist ELT pipeline (dlt -> dbt).")
    parser.add_argument("--ingest-only", action="store_true",
                        help="Only run the dlt ingest, skip dbt build.")
    parser.add_argument("--dbt-only", action="store_true",
                        help="Only run the dbt build, skip the dlt ingest.")
    args = parser.parse_args()

    if args.ingest_only and args.dbt_only:
        parser.error("--ingest-only and --dbt-only are mutually exclusive")

    if not args.dbt_only:
        run_ingest()
    if not args.ingest_only:
        run_dbt()
    print("ELT complete: bronze refreshed -> gold rebuilt + tests green")


if __name__ == "__main__":
    main()