-- Guard against the class of bug that overstated newly high-risk merchants ~3x:
-- new high-risk merchants may not jump more than max_new_high_risk_ratio x the prior month.
with m as (
    select score_month, new_high_risk,
           lag(new_high_risk) over (order by score_month) as prior_new
    from {{ ref('rpt_new_high_risk_by_month') }}
)
select *
from m
where prior_new >= 10
  and new_high_risk > {{ var('max_new_high_risk_ratio') }} * prior_new
