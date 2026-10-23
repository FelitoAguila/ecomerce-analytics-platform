import subprocess

from prefect import task

from config.paths import workspace_root

ELT_TIMEOUT_SECONDS = 2 * 60 * 60


@task(retries=1, retry_delay_seconds=10, log_prints=True)
def run_elt() -> None:
    try:
        result = subprocess.run(
            ["uv", "run", "--package", "olist-pipeline", "elt"],
            cwd=workspace_root(),
            check=True,
            capture_output=True,
            text=True,
            timeout=ELT_TIMEOUT_SECONDS,
        )
    except subprocess.CalledProcessError as exc:
        print(exc.stdout or "")
        print(exc.stderr or "")
        raise

    print(result.stdout)
    if result.stderr:
        print(result.stderr)
