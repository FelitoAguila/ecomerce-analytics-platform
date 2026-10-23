import sys

import pipeline.run_elt as run_elt
from pipeline.config import PipelineSettings


def test_pipeline_settings_defaults():
    p = PipelineSettings()
    assert p.name == "ecommerce_pipeline"
    assert p.dataset_name == "bronze_data"
    assert p.reconcile_name == "ecommerce_pipeline_reconcile"
    assert p.reconcile_dataset_name == "bronze_reconcile"


def test_main_ingest_only(mocker):
    mock_ingest = mocker.patch("pipeline.run_elt.run_ingest")
    mock_dbt = mocker.patch("pipeline.run_elt.run_dbt")
    mocker.patch.object(sys, "argv", ["elt", "--ingest-only"])
    run_elt.main()
    mock_ingest.assert_called_once()
    mock_dbt.assert_not_called()


def test_main_dbt_only(mocker):
    mock_ingest = mocker.patch("pipeline.run_elt.run_ingest")
    mock_dbt = mocker.patch("pipeline.run_elt.run_dbt")
    mocker.patch.object(sys, "argv", ["elt", "--dbt-only"])
    run_elt.main()
    mock_ingest.assert_not_called()
    mock_dbt.assert_called_once()


def test_main_mutual_exclusive(mocker):
    mocker.patch.object(sys, "argv", ["elt", "--ingest-only", "--dbt-only"])
    try:
        run_elt.main()
        assert False, "should exit"
    except SystemExit:
        pass
