with source as (

    {{ olist_staging_source('products') }}

),

deduplicated as (

    select
        product_id,
        product_category_name,
        product_name_lenght       as product_name_length,
        product_description_lenght as product_description_length,
        product_photos_qty,
        product_weight_g,
        product_length_cm,
        product_height_cm,
        product_width_cm,
        updated_at,
        row_number() over (
            partition by product_id
            order by updated_at desc, _dlt_load_id desc
        ) as rn
    from source

)

select
    product_id,
    product_category_name,
    product_name_length,
    product_description_length,
    product_photos_qty,
    product_weight_g,
    product_length_cm,
    product_height_cm,
    product_width_cm,
    updated_at
from deduplicated
where rn = 1
