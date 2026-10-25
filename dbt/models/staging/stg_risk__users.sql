select user_id, role
from {{ source('bronze', 'users') }}
