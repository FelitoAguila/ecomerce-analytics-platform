import re

import streamlit as st
from google.cloud import bigquery
from google.oauth2 import service_account

from dashboard.settings import get_settings

SCOPES = ["https://www.googleapis.com/auth/bigquery"]

_PARAM = re.compile(r"\$(\w+)")


@st.cache_resource(show_spinner="Connecting to BigQuery...")
def get_client() -> bigquery.Client:
    settings = get_settings()
    credentials = service_account.Credentials.from_service_account_file(
        settings.bigquery.keyfile, scopes=SCOPES
    )
    return bigquery.Client(
        project=settings.bigquery.project,
        credentials=credentials,
        location=settings.bigquery.location,
    )


def run_query(sql: str, params: dict | None = None):
    client = get_client()
    params = params or {}

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter(name, "STRING", value)
            for name, value in params.items()
        ]
    )

    portable_sql = _PARAM.sub(r"@\1", sql)
    return client.query(portable_sql, job_config=job_config).to_dataframe()
