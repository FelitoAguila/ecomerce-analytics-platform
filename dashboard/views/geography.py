import plotly.express as px
import streamlit as st

from dashboard import query


def page():
    st.header("Geography")

    geo = query.geo_state_centroids()
    states = query.states_with_metrics()

    merged = states.merge(geo, left_on="customer_state", right_on="geolocation_state", how="left")

    st.subheader("Orders & revenue by state")
    if not merged.empty:
        fig = px.scatter_geo(
            merged,
            lat="lat",
            lon="lng",
            size="orders",
            color="revenue",
            hover_name="customer_state",
            scope="south america",
            labels={"revenue": "revenue (R$)"},
        )
        st.plotly_chart(fig, width="stretch")

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Orders by state")
        if not states.empty:
            fig = px.bar(
                states.sort_values("orders", ascending=True).tail(15),
                x="orders",
                y="customer_state",
                orientation="h",
            )
            st.plotly_chart(fig, width="stretch")
    with c2:
        st.subheader("Revenue by state")
        if not states.empty:
            fig = px.bar(
                states.sort_values("revenue", ascending=True).tail(15),
                x="revenue",
                y="customer_state",
                orientation="h",
            )
            st.plotly_chart(fig, width="stretch")

    st.subheader("Top cities by customers")
    cities = query.top_cities()
    if not cities.empty:
        fig = px.bar(
            cities,
            x="customers",
            y="customer_city",
            orientation="h",
            color="customer_state",
        )
        st.plotly_chart(fig, width="stretch")