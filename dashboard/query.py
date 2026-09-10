import streamlit as st

from dashboard.settings import get_settings
from dashboard.connection import get_connection


@st.cache_data(ttl=300, show_spinner="Querying warehouse...")
def _cached(sql: str, params: tuple) -> object:
    conn = get_connection()
    if params:
        param_dict = {
            name: (list(value) if isinstance(value, tuple) else value)
            for name, value in params
        }
        return conn.execute(sql, param_dict).df()
    return conn.execute(sql).df()


def run(sql: str, **params):
    return _cached(sql, tuple(params.items()))


def tables():
    dashboard = get_settings().dashboard
    return {
        "fct_orders": dashboard.fct_orders,
        "fct_order_payments": dashboard.fct_order_payments,
        "dim_products": dashboard.dim_products,
        "dim_sellers": dashboard.dim_sellers,
        "dim_customers": dashboard.dim_customers,
        "orders_snapshot": dashboard.orders_snapshot,
        "geolocation": dashboard.geolocation,
        "order_items": dashboard.order_items,
    }


def kpis():
    t = tables()
    return run(
        f"""
        select
            count(*)                                as orders,
            round(sum(order_total_value), 2)        as revenue,
            round(sum(order_total_value) / count(*), 2) as avg_order_value,
            round(avg(delivery_days), 1)            as avg_delivery_days,
            round(100.0 * count(*) filter (where order_status = 'delivered') / count(*), 1)
                                                    as delivered_pct
        from {t['fct_orders']}
        """
    )


def monthly_metrics(start: str | None = None, end: str | None = None):
    t = tables()
    where = ""
    params = {}
    if start or end:
        bounds = []
        if start:
            bounds.append("order_purchase_timestamp >= cast($start as timestamp)")
            params["start"] = start
        if end:
            bounds.append("order_purchase_timestamp < cast($end as timestamp)")
            params["end"] = end
        where = "where " + " and ".join(bounds)
    return run(
        f"""
        select
            extract(year from order_purchase_timestamp)  as year,
            extract(month from order_purchase_timestamp) as month,
            count(*)                                     as orders,
            round(sum(order_total_value), 2)             as revenue
        from {t['fct_orders']}
        {where}
        group by 1, 2
        order by 1, 2
        """,
        **params,
    )


def status_funnel(start: str | None = None, end: str | None = None):
    t = tables()
    where = ""
    params = {}
    if start or end:
        bounds = []
        if start:
            bounds.append("order_purchase_timestamp >= cast($start as timestamp)")
            params["start"] = start
        if end:
            bounds.append("order_purchase_timestamp < cast($end as timestamp)")
            params["end"] = end
        where = "where " + " and ".join(bounds)
    return run(
        f"""
        select order_status, count(*) as orders
        from {t['fct_orders']}
        {where}
        group by order_status
        order by orders desc
        """,
        **params,
    )


def status_by_month(start: str | None = None, end: str | None = None):
    t = tables()
    where = ""
    params = {}
    if start or end:
        bounds = []
        if start:
            bounds.append("order_purchase_timestamp >= cast($start as timestamp)")
            params["start"] = start
        if end:
            bounds.append("order_purchase_timestamp < cast($end as timestamp)")
            params["end"] = end
        where = "and " + " and ".join(bounds)
    return run(
        f"""
        select
            extract(year from order_purchase_timestamp)  as year,
            extract(month from order_purchase_timestamp) as month,
            order_status,
            count(*)                                     as orders
        from {t['orders_snapshot']}
        where dbt_valid_to is null
        {where}
        group by 1, 2, 3
        order by 1, 2
        """,
        **params,
    )


def category_performance(limit: int = 12):
    t = tables()
    return run(
        f"""
        select
            coalesce(product_category_name_english, 'unclassified') as category,
            count(*)                                                as items_sold,
            round(sum(price), 2)                                    as revenue,
            round(avg(price), 2)                                    as avg_price
        from {t['order_items']}
        group by 1
        order by revenue desc
        limit {int(limit)}
        """
    )


def delivery_by_category():
    t = tables()
    return run(
        f"""
        select
            coalesce(i.product_category_name_english, 'unclassified') as category,
            round(avg(o.delivery_days), 1)                            as avg_delivery_days,
            count(distinct o.order_id)                                as orders
        from {t['order_items']} i
        join {t['fct_orders']} o on i.order_id = o.order_id
        where o.delivery_days is not null
        group by 1
        having count(distinct o.order_id) >= 100
        order by avg_delivery_days desc
        """
    )


def payment_split():
    t = tables()
    return run(
        f"""
        select
            payment_type,
            round(sum(payment_value), 2) as revenue,
            round(sum(payment_value) / sum(sum(payment_value)) over () * 100, 1) as share_pct
        from {t['fct_order_payments']}
        group by payment_type
        order by revenue desc
        """
    )


def installments_distribution():
    t = tables()
    return run(
        f"""
        select
            payment_installments,
            count(*)                        as payments,
            round(sum(payment_value), 2)    as revenue
        from {t['fct_order_payments']}
        group by payment_installments
        order by payment_installments
        """
    )


def top_sellers(limit: int = 10):
    t = tables()
    return run(
        f"""
        select
            i.seller_id,
            coalesce(s.seller_city, 'unknown')     as seller_city,
            coalesce(s.seller_state, 'unknown')     as seller_state,
            round(sum(i.price), 2)                  as revenue,
            count(distinct i.order_id)              as orders
        from {t['order_items']} i
        left join {t['dim_sellers']} s on i.seller_id = s.seller_id
        group by 1, 2, 3
        order by revenue desc
        limit {int(limit)}
        """
    )


def states_with_metrics():
    t = tables()
    return run(
        f"""
        select
            c.customer_state,
            count(distinct c.customer_unique_id)    as customers,
            count(distinct f.order_id)              as orders,
            round(sum(f.order_total_value), 2)      as revenue
        from {t['fct_orders']} f
        join {t['dim_customers']} c
            on f.customer_unique_id = c.customer_unique_id
        group by 1
        order by revenue desc
        """
    )


def geo_state_centroids():
    t = tables()
    return run(
        f"""
        select
            geolocation_state,
            avg(avg_lat) as lat,
            avg(avg_lng) as lng
        from {t['geolocation']}
        group by 1
        """
    )


def top_cities(limit: int = 10):
    t = tables()
    return run(
        f"""
        select
            customer_city,
            customer_state,
            count(distinct customer_unique_id) as customers
        from {t['dim_customers']}
        group by 1, 2
        order by customers desc
        limit {int(limit)}
        """
    )