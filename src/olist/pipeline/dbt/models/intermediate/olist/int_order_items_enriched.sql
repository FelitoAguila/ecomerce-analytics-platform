with order_items as (
    select * from {{ ref('stg_olist__order_items') }}
),

products as (
    select * from {{ ref('stg_olist__products') }}
),

sellers as (
    select * from {{ ref('stg_olist__sellers') }}
),

translation as (
    select * from {{ ref('stg_olist__product_category_name_translation') }}
)

select
    order_items.order_id,
    order_items.order_item_id,
    order_items.product_id,
    order_items.seller_id,
    products.product_category_name,
    coalesce(translation.product_category_name_english, products.product_category_name) as product_category_name_english,
    products.product_name_length,
    order_items.price,
    order_items.freight_value,
    sellers.seller_city,
    sellers.seller_state,
    order_items.shipping_limit_date
from order_items
left join products
    on order_items.product_id = products.product_id
left join sellers
    on order_items.seller_id = sellers.seller_id
left join translation
    on products.product_category_name = translation.product_category_name