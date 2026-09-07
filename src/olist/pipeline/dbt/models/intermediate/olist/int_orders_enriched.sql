with orders as (
    select * from {{ ref('stg_olist__orders') }}
),

customers as (
    select * from {{ ref('stg_olist__customers') }}
)

select
    orders.order_id,
    orders.customer_id,
    customers.customer_unique_id,
    customers.customer_city,
    customers.customer_state,
    orders.order_status,
    orders.order_purchase_timestamp,
    orders.order_approved_at,
    orders.order_delivered_carrier_date,
    orders.order_delivered_customer_date,
    orders.order_estimated_delivery_date,
    -- derived metrics (business logic lives here)
    datediff('day', orders.order_purchase_timestamp,
             orders.order_delivered_customer_date) as delivery_days,
    datediff('hour', orders.order_purchase_timestamp,
             orders.order_approved_at) as approval_hours
from orders
left join customers
    on orders.customer_id = customers.customer_id