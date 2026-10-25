-- Each merchant's rating in the latest (open) month: what the snapshot tracks between runs, so a rating
-- changed by an override after a build is kept in history (snapshots/snap_current_ratings).
select merchant_id, period_month, risk_score, model_rating, final_rating, rating_source, override_id
from {{ ref('fct_merchant_rating') }}
where period_month = (select max(period_month) from {{ ref('fct_merchant_rating') }})
