with source as (

    {{ olist_staging_source('product_category_name_translation') }}

),

deduplicated as (

    select
        product_category_name,
        product_category_name_english,
        updated_at,
        row_number() over (
            partition by product_category_name
            order by updated_at desc, _dlt_load_id desc
        ) as rn
    from source

)

select
    product_category_name,
    product_category_name_english,
    updated_at
from deduplicated
where rn = 1
