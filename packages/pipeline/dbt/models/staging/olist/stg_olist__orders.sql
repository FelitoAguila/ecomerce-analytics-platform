with source as (

    {{ olist_staging_source('orders') }}

),

deduplicated as (

    select
        order_id,
        customer_id,
        order_status,
        order_purchase_timestamp,
        order_approved_at,
        order_delivered_carrier_date,
        order_delivered_customer_date,
        order_estimated_delivery_date,
        updated_at,
        row_number() over (
            partition by order_id
            order by updated_at desc, _dlt_load_id desc
        ) as rn
    from source

)

select
    order_id,
    customer_id,
    order_status,
    order_purchase_timestamp,
    order_approved_at,
    order_delivered_carrier_date,
    order_delivered_customer_date,
    order_estimated_delivery_date,
    updated_at
from deduplicated
where rn = 1
