{% snapshot orders_snapshot %}

{{
    config(
        target_schema='main_snapshots',
        unique_key='order_id',
        strategy='timestamp',
        updated_at='updated_at',
    )
}}

select * from {{ ref('stg_olist__orders') }}

{% endsnapshot %}