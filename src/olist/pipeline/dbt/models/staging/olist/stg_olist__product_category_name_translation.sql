with source as (
    select * from {{ source('ecommerce_data', 'product_category_name_translation') }}
),

renamed as (
    select
        product_category_name,
        product_category_name_english,
        updated_at
    from source
)

select * from renamed