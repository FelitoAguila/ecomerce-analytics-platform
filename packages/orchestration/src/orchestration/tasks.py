import subprocess

from prefect import task

from config.paths import workspace_root


@task(retries=1, retry_delay_seconds=10)
def run_elt() -> None:
    result = subprocess.run(
        ["uv", "run", "--package", "olist-pipeline", "elt"],
        cwd=workspace_root(),
        check=True,
        capture_output=True,
        text=True,
    )
    print(result.stdout)
    if result.stderr:
        print(result.stderr)
