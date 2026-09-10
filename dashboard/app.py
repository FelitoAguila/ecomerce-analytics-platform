import streamlit as st

from dashboard.views import geography, orders, overview
from dashboard.settings import get_settings

st.set_page_config(
    page_title="Olist Analytics",
    page_icon=":shopping_cart:",
    layout="wide",
)

st.sidebar.title("Olist Analytics")
settings = get_settings()
st.sidebar.caption(
    f"Source: {settings.dashboard.source}"
    + (
        f" ({settings.warehouse_local.path})"
        if settings.dashboard.source == "duckdb"
        else ""
    )
)
if st.sidebar.button("Refresh data"):
    st.cache_data.clear()
    st.cache_resource.clear()

pages = st.navigation(
    [
        st.Page(overview.page, title="Overview", url_path="overview", default=True),
        st.Page(orders.page, title="Orders", url_path="orders"),
        st.Page(geography.page, title="Geography", url_path="geography"),
    ]
)
pages.run()