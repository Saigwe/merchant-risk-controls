-- High-risk merchants per month, split into those carried over from the previous month and those new
-- to high risk. "New" means not rated high in the immediately preceding month (or not active then).
-- The 3x bug this guards against: if the prior-month join silently matches nothing, every high merchant
-- looks new. The reconciliation test checks total = new + continuing and continuing <= last month's total.
with r as (
    select
        merchant_id,
        period_month,
        final_rating,
        lag(final_rating) over (partition by merchant_id order by period_month) as prior_rating,
        lag(period_month) over (partition by merchant_id order by period_month) as prior_month
    from {{ ref('fct_merchant_rating') }}
),

flagged as (
    select
        *,
        coalesce(
            final_rating = 'high'
            and prior_rating = 'high'
            and prior_month = cast({{ dbt.dateadd('month', -1, 'period_month') }} as date),
            false
        ) as is_continuing_high
    from r
)

select
    period_month,
    count(*)                                                                    as merchants_rated,
    count(*) filter (where final_rating = 'high')                               as total_high,
    count(*) filter (where is_continuing_high)                                  as continuing_high,
    count(*) filter (where final_rating = 'high' and not is_continuing_high)    as new_high,
    count(*) filter (where final_rating = 'high' and prior_month is null)       as new_high_newly_onboarded
from flagged
group by 1
