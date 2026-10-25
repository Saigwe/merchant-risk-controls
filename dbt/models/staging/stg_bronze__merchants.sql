select
    merchant_id,
    segment,
    country_code
from {{ source('bronze', 'merchants') }}
