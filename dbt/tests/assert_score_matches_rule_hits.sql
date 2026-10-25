-- Every score equals its rule points (capped at 100), and every rule that fired is listed as a reason.
with points as (
    select merchant_id, period_month, sum(points) as points, count(*) as rules
    from {{ ref('fct_rule_hits') }}
    group by 1, 2
)

select s.merchant_id, s.period_month
from {{ ref('fct_merchant_risk_score') }} s
left join points p on p.merchant_id = s.merchant_id and p.period_month = s.period_month
where s.risk_score <> least(100, coalesce(p.points, 0))
   or coalesce(len(string_split(s.rules_fired, ', ')), 0) <> coalesce(p.rules, 0)
