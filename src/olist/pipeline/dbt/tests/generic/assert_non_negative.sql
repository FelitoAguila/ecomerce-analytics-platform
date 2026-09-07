{% test assert_non_negative(model, column_name) %}

select
    {{ column_name }} as non_negative_column
from {{ model }}
where {{ column_name }} < 0

{% endtest %}