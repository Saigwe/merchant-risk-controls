-- Type-2 history of each merchant's final rating: one row per unbroken run of months at the same rating
-- (gaps-and-islands: the difference of two row numbers is constant within a run).
with r as (
    select
        merchant_id,
        period_month,
        final_rating,
        row_number() over (partition by merchant_id order by period_month)
          - row_number() over (partition by merchant_id, final_rating order by period_month) as island
    from {{ ref('fct_merchant_rating') }}
),

latest as (
    select max(period_month) as period_month from {{ ref('fct_merchant_rating') }}
)

select
    r.merchant_id,
    r.final_rating,
    min(r.period_month)                         as valid_from_month,
    max(r.period_month)                         as valid_to_month,
    count(*)                                    as months,
    max(r.period_month) = max(l.period_month)   as is_current
from r
cross join latest l
group by r.merchant_id, r.final_rating, r.island
