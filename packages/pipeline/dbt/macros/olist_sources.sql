{#
  Union the append-only bronze dataset with the reconciliation dataset.

  The bronze dataset is loaded incrementally with an "open" cursor range, so it
  only ever receives rows strictly newer than the watermark. A reconciliation
  run re-reads a bounded window of the source and merges it by primary key into
  the separate bronze_reconcile dataset, which recovers rows the incremental
  watermark skipped.

  The reconcile tables only exist after the first backfill, so the second branch
  is emitted only when the relation is present. This keeps the project buildable
  before the first reconciliation run.
#}
{% macro olist_staging_source(table_name) %}
    {%- set bronze = source('ecommerce_data', table_name) -%}
    {%- set reconcile = source('ecommerce_data_reconcile', table_name) -%}
    {%- set reconcile_relation = adapter.get_relation(
        database=target.database,
        schema=reconcile.schema,
        identifier=reconcile.identifier
    ) -%}

    select * from {{ bronze }}
    {%- if reconcile_relation is not none %}
    union all
    select * from {{ reconcile }}
    {%- endif %}
{% endmacro %}
