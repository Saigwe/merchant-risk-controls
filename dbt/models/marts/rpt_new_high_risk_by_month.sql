-- Merchants newly rated high in each month (high now, not high the month before).
with r as (
    select
        merchant_id,
        score_month,
        final_rating,
        lag(final_rating) over (partition by merchant_id order by score_month) as prior_rating
    from {{ ref('fct_merchant_risk_rating') }}
)

select
    score_month,
    count(*) filter (where final_rating = 'high' and coalesce(prior_rating, '') <> 'high') as new_high_risk,
    count(*) filter (where final_rating = 'high')                                         as total_high_risk
from r
group by 1
