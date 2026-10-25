select
    merchant_id,
    cast(period_month as date)                  as period_month,
    cast(gmv_usd as decimal(18, 2))             as gmv_usd,
    orders,
    chargebacks,
    refunds,
    negative_balance_days,
    ownership_changed,
    kyc_expired
from {{ source('bronze', 'merchant_monthly_metrics') }}
