select
    override_id,
    merchant_id,
    cast(score_month as date)               as score_month,
    proposed_rating,
    reason,
    proposed_by,
    status,
    approved_by
from {{ source('bronze', 'overrides') }}
