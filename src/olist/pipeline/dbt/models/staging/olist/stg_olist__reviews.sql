with source as (
    select * from {{ source('ecommerce_data', 'reviews') }}
),

deduplicated as (
    select
        review_id,
        order_id,
        review_score,
        review_comment_title,
        review_comment_message,
        review_creation_date,
        review_answer_timestamp,
        updated_at,
        row_number() over (
            partition by review_id, order_id
            order by updated_at desc
        ) as rn
    from source
)

select
    review_id,
    order_id,
    review_score,
    review_comment_title,
    review_comment_message,
    review_creation_date,
    review_answer_timestamp,
    updated_at
from deduplicated
where rn = 1