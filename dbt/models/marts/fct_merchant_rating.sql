-- One row per merchant and month: model rating, the approved override (if any), and the final rating.
with approved as (
    select *
    from {{ ref('int_override_status') }}
    where status = 'approved'
    qualify row_number() over (partition by merchant_id, period_month order by decided_at desc, override_id desc) = 1
)

select
    s.merchant_id,
    s.period_month,
    s.risk_score,
    s.model_rating,
    s.rules_fired,
    a.override_id,
    a.proposed_rating                                       as override_rating,
    coalesce(a.proposed_rating, s.model_rating)             as final_rating,
    case when a.override_id is null then 'model' else 'override' end as rating_source
from {{ ref('fct_merchant_risk_score') }} s
left join approved a on a.merchant_id = s.merchant_id and a.period_month = s.period_month
