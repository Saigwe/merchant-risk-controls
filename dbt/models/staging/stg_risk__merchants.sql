select
    merchant_id,
    segment,
    country_code,
    category,
    cast(onboarded_at as date) as onboarded_date
from {{ source('bronze', 'merchants') }}
