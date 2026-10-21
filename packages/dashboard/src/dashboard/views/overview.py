import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard import query


def page():
    st.header("Overview")

    kpi = query.kpis().iloc[0]

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Orders", f"{int(kpi['orders']):,}")
    c2.metric("Revenue", f"R$ {kpi['revenue']:,.2f}")
    c3.metric("Avg order value", f"R$ {kpi['avg_order_value']:,.2f}")
    c4.metric("Avg delivery (days)", kpi["avg_delivery_days"])
    c5.metric("Delivered", f"{kpi['delivered_pct']}%")

    monthly = query.monthly_metrics()
    monthly["month"] = pd.to_datetime(
        dict(year=monthly["year"], month=monthly["month"], day=1)
    )

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Orders per month")
        fig = px.bar(monthly, x="month", y="orders")
        st.plotly_chart(fig, width="stretch")
    with c2:
        st.subheader("Revenue per month")
        fig = px.bar(monthly, x="month", y="revenue")
        st.plotly_chart(fig, width="stretch")

    st.subheader("Order status funnel")
    funnel = query.status_funnel()
    fig = px.bar(funnel, x="orders", y="order_status", orientation="h")
    st.plotly_chart(fig, width="stretch")

    st.subheader("Top categories")
    cat = query.category_performance()
    fig = px.bar(cat, x="revenue", y="category", orientation="h")
    st.plotly_chart(fig, width="stretch")