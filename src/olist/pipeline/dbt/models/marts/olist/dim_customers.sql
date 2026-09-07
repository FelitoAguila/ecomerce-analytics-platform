with customers as (
    select * from {{ ref('stg_olist__customers') }}
)

select
    customer_unique_id,
    min(customer_city)     as customer_city,
    min(customer_state)    as customer_state
from customers
group by customer_unique_id