with source as (

    {{ olist_staging_source('geolocation') }}

),

deduplicated as (

    select
        geolocation_id,
        geolocation_zip_code_prefix,
        geolocation_lat,
        geolocation_lng,
        geolocation_city,
        geolocation_state,
        updated_at,
        row_number() over (
            partition by geolocation_id
            order by updated_at desc
        ) as rn
    from source

)

select
    geolocation_id,
    geolocation_zip_code_prefix,
    geolocation_lat,
    geolocation_lng,
    geolocation_city,
    geolocation_state,
    updated_at
from deduplicated
where rn = 1
