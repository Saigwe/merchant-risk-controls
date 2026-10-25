-- Override workload and outcomes per month.
with o as (
    select period_month, status, hours_to_decision from {{ ref('int_override_status') }}
),

rated as (
    select period_month, count(*) as merchants_rated,
           count(*) filter (where rating_source = 'override') as ratings_overridden,
           count(*) filter (where rating_source = 'override' and final_rating <> model_rating) as ratings_changed
    from {{ ref('fct_merchant_rating') }}
    group by 1
)

select
    r.period_month,
    r.merchants_rated,
    count(o.status)                                                         as proposals,
    count(*) filter (where o.status = 'approved')                           as approved,
    count(*) filter (where o.status = 'rejected')                           as rejected,
    count(*) filter (where o.status = 'withdrawn')                          as withdrawn,
    count(*) filter (where o.status = 'proposed')                           as pending,
    cast(count(*) filter (where o.status = 'approved') as double)
        / nullif(count(*) filter (where o.status in ('approved', 'rejected')), 0) as approval_rate,
    median(o.hours_to_decision)                                             as median_hours_to_decision,
    r.ratings_overridden,
    r.ratings_changed,
    cast(r.ratings_overridden as double) / r.merchants_rated                as override_share
from rated r
left join o on o.period_month = r.period_month
group by r.period_month, r.merchants_rated, r.ratings_overridden, r.ratings_changed
