-- One row per merchant and month: score (sum of rule points, capped at 100), model rating, and the rules
-- behind it, highest weight first (what an analyst sees as the reason for the rating).
with hits as (
    select
        merchant_id,
        period_month,
        sum(points)                                         as points,
        string_agg(rule_id, ', ' order by points desc, rule_id) as rules_fired
    from {{ ref('fct_rule_hits') }}
    group by 1, 2
)

select
    m.merchant_id,
    m.period_month,
    least(100, coalesce(h.points, 0))                       as risk_score,
    case
        when least(100, coalesce(h.points, 0)) >= {{ var('high_risk_threshold') }} then 'high'
        when least(100, coalesce(h.points, 0)) >= {{ var('medium_risk_threshold') }} then 'medium'
        else 'low'
    end                                                     as model_rating,
    h.rules_fired
from {{ ref('stg_risk__monthly_metrics') }} m
left join hits h on h.merchant_id = m.merchant_id and h.period_month = m.period_month
