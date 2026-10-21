import argparse

from prefect import flow

from orchestration.tasks import run_elt


@flow(log_prints=True)
def elt_flow() -> None:
    run_elt()
    print("ELT flow complete: bronze refreshed -> gold rebuilt + tests green")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Olist ELT flow (dlt -> dbt).")
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Serve the flow as the scheduled 'elt-daily' deployment (daily 07:00).",
    )
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
