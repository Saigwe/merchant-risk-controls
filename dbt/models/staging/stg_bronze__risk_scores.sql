select
    merchant_id,
    cast(score_month as date)             as score_month,
    risk_score,
    model_version
from {{ source('bronze', 'risk_scores') }}
