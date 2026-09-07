with order_items as (
    select * from {{ ref('stg_olist__order_items') }}
)

select
    order_id,
    count(*) as item_count,
    sum(price) as items_total_value,
    sum(freight_value) as items_total_freight,
    sum(price + freight_value) as order_total_value,
    avg(price) as avg_item_value
from order_items
group by order_id