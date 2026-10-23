import subprocess
from pathlib import Path

import orchestration.flows as flows
import orchestration.tasks as tasks
from prefect.client.schemas.schedules import CronSchedule


def test_elt_flow_exists():
    assert hasattr(flows, "elt_flow")


def test_run_elt_task_exists():
    assert hasattr(tasks, "run_elt")


def test_run_elt_timeout_constant():
    assert tasks.ELT_TIMEOUT_SECONDS == 7200


def test_run_elt_task_metadata():
    t = tasks.run_elt
    assert getattr(t, "retries", None) == 1
    assert getattr(t, "retry_delay_seconds", None) == 10
    assert getattr(t, "log_prints", None) is True


def test_run_elt_success(mocker):
    mock_run = mocker.patch("orchestration.tasks.subprocess.run")
    mock_run.return_value = subprocess.CompletedProcess(["uv", "run", "elt"], 0, stdout="ok\n", stderr="")
    mock_root = mocker.patch("orchestration.tasks.workspace_root", return_value=Path("/repo"))
    tasks.run_elt.fn()
    mock_root.assert_called_once()
    args, kwargs = mock_run.call_args
    assert args[0] == ["uv", "run", "--package", "olist-pipeline", "elt"]
    assert kwargs["cwd"] == Path("/repo")
    assert kwargs["check"] is True
    assert kwargs["capture_output"] is True
    assert kwargs["text"] is True
    assert kwargs["timeout"] == 7200


def test_run_elt_failure_prints_and_raises(mocker, capsys):
    exc = subprocess.CalledProcessError(1, ["uv"], output="out\n", stderr="err\n")
    mocker.patch("orchestration.tasks.subprocess.run", side_effect=exc)
    mocker.patch("orchestration.tasks.workspace_root", return_value=Path("/repo"))
    try:
        tasks.run_elt.fn()
        assert False, "should have raised"
    except subprocess.CalledProcessError:
        pass
    captured = capsys.readouterr()
    assert "out" in captured.out
    assert "err" in captured.out


def test_flow_schedule_timezone():
    s = CronSchedule(cron="0 7 * * *", timezone="America/Sao_Paulo")
    assert s.timezone == "America/Sao_Paulo"
