-- Independent audit of the override log: re-checks every workflow control in SQL over all events, so a
-- write that bypassed the app (or a bug in it) is still caught. One row per event and broken control.
{% set min_len = var('min_reason_length') %}
with e as (
    select
        ev.*,
        u.role,
        l.locked_at,
        first_value(ev.actor) over (partition by ev.override_id order by ev.event_id) as proposer,
        lag(ev.action) over (partition by ev.override_id order by ev.event_id)        as prior_action
    from {{ ref('stg_risk__override_events') }} ev
    left join {{ ref('stg_risk__users') }} u on u.user_id = ev.actor
    left join {{ ref('stg_risk__period_locks') }} l on l.period_month = ev.period_month
),

approved_live as (
    select
        override_id,
        row_number() over (partition by merchant_id, period_month order by decided_at, override_id) as nth_approved
    from {{ ref('int_override_status') }}
    where status = 'approved'
),

violations as (
    select event_id, override_id, 'unknown_user' as violation from e where role is null
    union all
    select event_id, override_id, 'locked_period_edit' from e where locked_at is not null and event_ts >= locked_at
    union all
    select event_id, override_id, 'missing_reason' from e
    where action in ('propose', 'reject', 'withdraw') and length(coalesce(reason, '')) < {{ min_len }}
    union all
    select event_id, override_id, 'self_approval' from e
    where action in ('approve', 'reject') and actor = proposer
    union all
    select event_id, override_id, 'unauthorised_approver' from e
    where action in ('approve', 'reject') and coalesce(role, '') <> 'checker'
    union all
    select event_id, override_id, 'withdraw_by_non_proposer' from e where action = 'withdraw' and actor <> proposer
    union all
    select event_id, override_id, 'invalid_sequence' from e
    where (action = 'propose' and prior_action is not null)
       or (action <> 'propose' and coalesce(prior_action, '') <> 'propose')
    union all
    select e.event_id, e.override_id, 'duplicate_live_override'
    from e
    join approved_live a on a.override_id = e.override_id and a.nth_approved > 1
    where e.action = 'approve'
)

select
    v.event_id,
    v.override_id,
    v.violation,
    e.merchant_id,
    e.period_month,
    e.action,
    e.actor,
    e.event_ts
from violations v
join e on e.event_id = v.event_id
