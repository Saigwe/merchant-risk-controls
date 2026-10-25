-- Each merchant-month's risk signals in long form (one row per signal), so the rules table can be
-- joined on signal name and scoring needs no per-rule SQL.
{% set signals = ['chargeback_rate', 'refund_rate', 'negative_balance_days', 'tenure_days',
                  'ownership_changed_3m', 'kyc_expired', 'gmv_growth'] %}
with wide as (
    select
        m.merchant_id,
        m.period_month,
        cast(m.chargebacks as double) / nullif(m.orders, 0)                             as chargeback_rate,
        cast(m.refunds as double) / nullif(m.orders, 0)                                 as refund_rate,
        cast(m.negative_balance_days as double)                                         as negative_balance_days,
        cast({{ dbt.datediff('mer.onboarded_date', dbt.last_day('m.period_month', 'month'), 'day') }} as double) as tenure_days,
        cast(max(cast(m.ownership_changed as integer)) over (
            partition by m.merchant_id order by m.period_month rows between 2 preceding and current row
        ) as double)                                                                    as ownership_changed_3m,
        cast(cast(m.kyc_expired as integer) as double)                                  as kyc_expired,
        cast(m.gmv_usd as double) / nullif(lag(cast(m.gmv_usd as double)) over (
            partition by m.merchant_id order by m.period_month), 0) - 1                 as gmv_growth
    from {{ ref('stg_risk__monthly_metrics') }} m
    join {{ ref('stg_risk__merchants') }} mer on mer.merchant_id = m.merchant_id
)

{% for s in signals %}
select merchant_id, period_month, '{{ s }}' as signal, {{ s }} as value from wide
{% if not loop.last %}union all{% endif %}
{% endfor %}
