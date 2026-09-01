with source as (
    select * from {{ source('ecommerce_data', 'order_items') }}
),

deduplicated as (
    select
        order_id,
        order_item_id,
        product_id,
        seller_id,
        shipping_limit_date,
        price,
        freight_value,
        updated_at,
        row_number() over (
            partition by order_id, order_item_id
            order by updated_at desc
        ) as rn
    from source
)

select
    order_id,
    order_item_id,
    product_id,
    seller_id,
    shipping_limit_date,
    price,
    freight_value,
    updated_at
from deduplicated
where rn = 1