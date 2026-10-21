import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard import query


def page():
    st.header("Orders")

    with st.sidebar:
        start = st.date_input("From", pd.to_datetime("2016-09-01").date())
        end = st.date_input("To", pd.to_datetime("2018-09-30").date())

    params = {
        "start": start.isoformat(),
        "end": end.isoformat(),
    }

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Status over time (purchase cohort, current status)")
        cohort = query.status_by_month(start=params["start"], end=params["end"])
        cohort["month"] = pd.to_datetime(
            dict(year=cohort["year"], month=cohort["month"], day=1)
        )
        if not cohort.empty:
            fig = px.area(
                cohort,
                x="month",
                y="orders",
                color="order_status",
                line_group="order_status",
            )
            st.plotly_chart(fig, width="stretch")
    with c2:
        st.subheader("Current funnel")
        funnel = query.status_funnel(start=params["start"], end=params["end"])
        if not funnel.empty:
            fig = px.pie(funnel, names="order_status", values="orders")
            st.plotly_chart(fig, width="stretch")

    st.subheader("Delivery performance by category")
    delivery = query.delivery_by_category()
    if not delivery.empty:
        fig = px.bar(
            delivery,
            x="category",
            y="avg_delivery_days",
            color="orders",
            labels={"avg_delivery_days": "avg delivery days"},
        )
        st.plotly_chart(fig, width="stretch")

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Payment mix")
        pay = query.payment_split()
        if not pay.empty:
            fig = px.pie(pay, names="payment_type", values="revenue", hole=0.4)
            st.plotly_chart(fig, width="stretch")
    with c2:
        st.subheader("Installments")
        inst = query.installments_distribution()
        if not inst.empty:
            fig = px.bar(inst, x="payment_installments", y="payments")
            st.plotly_chart(fig, width="stretch")