-- The guard against the "3x newly high-risk" class of bug:
-- 1. every high merchant is either new or continuing (total = new + continuing)
-- 2. continuing can't exceed last month's high total
-- 3. new high-risk can't jump more than max_new_high_risk_ratio x the previous month (when that is >= 10)
with m as (
    select
        *,
        lag(total_high) over (order by period_month) as prior_total_high,
        lag(new_high) over (order by period_month)   as prior_new_high
    from {{ ref('rpt_new_high_risk') }}
)

select period_month, 'total <> new + continuing' as problem from m where total_high <> new_high + continuing_high
union all
select period_month, 'continuing exceeds last month total' from m where continuing_high > coalesce(prior_total_high, 0)
union all
select period_month, 'new high-risk spiked' from m
where prior_new_high >= 10 and new_high > {{ var('max_new_high_risk_ratio') }} * prior_new_high
