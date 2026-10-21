with source as (
    select * from {{ source('ecommerce_data', 'sellers') }}
),

renamed as (
    select
        seller_id,
        seller_zip_code_prefix,
        seller_city,
        seller_state,
        updated_at
    from source
)

select * from renamed