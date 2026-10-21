with source as (

    {{ olist_staging_source('customers') }}

),

deduplicated as (

    select
        customer_id,
        customer_unique_id,
        customer_zip_code_prefix,
        customer_city,
        customer_state,
        updated_at,
        row_number() over (
            partition by customer_id
            order by updated_at desc
        ) as rn
    from source

)

select
    customer_id,
    customer_unique_id,
    customer_zip_code_prefix,
    customer_city,
    customer_state,
    updated_at
from deduplicated
where rn = 1
