with source as (
    select * from {{ source('ecommerce_data', 'order_payments') }}
),

deduplicated as (
    select
        order_id,
        payment_sequential,
        payment_type,
        payment_installments,
        payment_value,
        updated_at,
        row_number() over (
            partition by order_id, payment_sequential
            order by updated_at desc
        ) as rn
    from source
)

select
    order_id,
    payment_sequential,
    payment_type,
    payment_installments,
    payment_value,
    updated_at
from deduplicated
where rn = 1