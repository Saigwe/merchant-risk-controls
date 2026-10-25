-- An append-only log has event ids that only go forward in time: a later id never has an earlier timestamp.
select event_id, event_ts, prior_ts
from (
    select event_id, event_ts, lag(event_ts) over (order by event_id) as prior_ts
    from {{ ref('stg_risk__override_events') }}
)
where event_ts < prior_ts
