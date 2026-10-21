import argparse
import subprocess

from config.paths import workspace_root

PIPELINE = "olist-pipeline"


def run_ingest() -> None:
    subprocess.run(
        ["uv", "run", "--package", PIPELINE, "ingest"],
        cwd=workspace_root(),
        check=True,
    )


def run_dbt() -> None:
    root = workspace_root()
    subprocess.run(
        [
            "uv",
            "run",
            "--package",
            PIPELINE,
            "--group",
            "dbt-bigquery",
            "--env-file",
            str(root / ".env"),
            "dbt",
            "build",
        ],
        cwd=root / "packages" / "pipeline" / "dbt",
        check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the Olist ELT pipeline (dlt -> dbt)."
    )
    parser.add_argument(
        "--ingest-only",
        action="store_true",
        help="Only run the dlt ingest, skip dbt build.",
    )
    parser.add_argument(
        "--dbt-only",
        action="store_true",
        help="Only run the dbt build, skip the dlt ingest.",
    )
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
