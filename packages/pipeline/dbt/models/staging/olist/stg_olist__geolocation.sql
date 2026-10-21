with source as (
    select * from {{ source('ecommerce_data', 'geolocation') }}
),

renamed as (
    select
        geolocation_id,
        geolocation_zip_code_prefix,
        geolocation_lat,
        geolocation_lng,
        geolocation_city,
        geolocation_state,
        updated_at
    from source
)

select * from renamed