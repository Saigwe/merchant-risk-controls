-- One row per merchant, month and rule that fired, with the signal value that triggered it.
select
    s.merchant_id,
    s.period_month,
    r.rule_id,
    r.description,
    r.points,
    s.signal,
    s.value,
    r.threshold
from {{ ref('int_merchant_signals') }} s
join {{ ref('risk_rules') }} r on r.signal = s.signal
where s.value is not null
  and (
        (r.operator = '>=' and s.value >= r.threshold)
     or (r.operator = '<'  and s.value <  r.threshold)
  )
