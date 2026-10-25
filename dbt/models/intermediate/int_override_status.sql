-- Current state of each override, replayed from the append-only event log.
with ordered as (
    select
        e.*,
        row_number() over (partition by e.override_id order by e.event_id desc) as recency
    from {{ ref('stg_risk__override_events') }} e
),

proposals as (
    select override_id, merchant_id, period_month, actor as proposed_by, event_ts as proposed_at,
           proposed_rating, reason
    from ordered
    where action = 'propose'
    qualify row_number() over (partition by override_id order by event_id) = 1
)

select
    p.override_id,
    p.merchant_id,
    p.period_month,
    p.proposed_by,
    p.proposed_at,
    p.proposed_rating,
    p.reason,
    case l.action
        when 'propose' then 'proposed'
        when 'approve' then 'approved'
        when 'reject' then 'rejected'
        when 'withdraw' then 'withdrawn'
    end                                                                         as status,
    case when l.action in ('approve', 'reject') then l.actor end                as decided_by,
    case when l.action <> 'propose' then l.event_ts end                         as decided_at,
    case when l.action <> 'propose'
         then {{ dbt.datediff('p.proposed_at', 'l.event_ts', 'minute') }} / 60.0 end as hours_to_decision
from proposals p
join ordered l on l.override_id = p.override_id and l.recency = 1
