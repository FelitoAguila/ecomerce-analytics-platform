with source as (

    {{ olist_staging_source('sellers') }}

),

deduplicated as (

    select
        seller_id,
        seller_zip_code_prefix,
        seller_city,
        seller_state,
        updated_at,
        row_number() over (
            partition by seller_id
            order by updated_at desc, _dlt_load_id desc
        ) as rn
    from source

)

select
    seller_id,
    seller_zip_code_prefix,
    seller_city,
    seller_state,
    updated_at
from deduplicated
where rn = 1
