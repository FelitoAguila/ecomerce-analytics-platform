with payments as (
    select * from {{ ref('stg_olist__order_payments') }}
)

select
    order_id,
    payment_sequential,
    payment_type,
    payment_installments,
    payment_value
from payments