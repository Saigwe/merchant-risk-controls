select
    event_id,
    override_id,
    merchant_id,
    cast(period_month as date)      as period_month,
    action,
    actor,
    cast(event_ts as timestamp)     as event_ts,
    nullif(trim(reason), '')        as reason,
    proposed_rating
from {{ source('bronze', 'override_events') }}
