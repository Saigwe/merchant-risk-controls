select
    cast(period_month as date)      as period_month,
    cast(locked_at as timestamp)    as locked_at,
    locked_by
from {{ source('bronze', 'period_locks') }}
