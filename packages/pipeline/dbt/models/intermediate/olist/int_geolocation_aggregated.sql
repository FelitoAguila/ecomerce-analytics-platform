with geolocation as (
    select * from {{ ref('stg_olist__geolocation') }}
)

select
    geolocation_city,
    geolocation_state,
    avg(geolocation_lat) as avg_lat,
    avg(geolocation_lng) as avg_lng,
    count(*) as location_count
from geolocation
group by geolocation_city, geolocation_state