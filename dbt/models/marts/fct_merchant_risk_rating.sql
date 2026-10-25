-- One row per merchant and month: model rating, the approved override (if any) and the final rating.
with scores as (
    select
        merchant_id,
        score_month,
        risk_score,
        case
            when risk_score >= {{ var('high_risk_threshold') }} then 'high'
            when risk_score >= {{ var('medium_risk_threshold') }} then 'medium'
            else 'low'
        end as model_rating
    from {{ ref('stg_bronze__risk_scores') }}
),

approved as (
    select *
    from {{ ref('stg_bronze__overrides') }}
    where status = 'approved'
    qualify row_number() over (partition by merchant_id, score_month order by override_id desc) = 1
)

select
    s.merchant_id,
    s.score_month,
    s.risk_score,
    s.model_rating,
    a.override_id,
    a.proposed_rating                           as override_rating,
    coalesce(a.proposed_rating, s.model_rating) as final_rating,
    case when a.override_id is null then 'model' else 'override' end as rating_source
from scores s
left join approved a
    on a.merchant_id = s.merchant_id
    and a.score_month = s.score_month
