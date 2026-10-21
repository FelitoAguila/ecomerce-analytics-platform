import streamlit as st
import duckdb

from dashboard.settings import get_settings


@st.cache_resource(show_spinner="Connecting to warehouse...")
def get_connection() -> duckdb.DuckDBPyConnection:
    settings = get_settings()
    source = settings.dashboard.source

    if source == "duckdb":
        return duckdb.connect(settings.warehouse_local.path, read_only=True)

    if source == "bigquery":
        raise NotImplementedError(
            "BigQuery read support lands in Phase 7. "
            "For now set DASHBOARD__SOURCE=duckdb."
        )

    raise ValueError(f"Unknown dashboard source: {source!r}")


def run_query(sql: str, params: dict | None = None):
    conn = get_connection()
    return conn.execute(sql, params or {}).df()