with orders as (
    select * from {{ ref('int_orders_enriched') }}
),

order_totals as (
    select * from {{ ref('int_order_items_aggregated') }}
)

select
    orders.order_id,
    orders.customer_unique_id,
    orders.order_status,
    orders.order_purchase_timestamp,
    orders.order_approved_at,
    orders.order_delivered_customer_date,
    orders.delivery_days,
    orders.approval_hours,
    coalesce(order_totals.item_count, 0)          as item_count,
    coalesce(order_totals.order_total_value, 0)   as order_total_value,
    coalesce(order_totals.items_total_freight, 0) as total_freight
from orders
left join order_totals
    on orders.order_id = order_totals.order_id