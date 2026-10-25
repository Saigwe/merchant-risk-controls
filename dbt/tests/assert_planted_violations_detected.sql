-- Answer key (CI fixture only): every planted violation is reported with the right control,
-- and no override outside the answer key is flagged.
{{ config(enabled=var('is_fixture', false)) }}
with planted as (
    select * from {{ source('bronze', 'fixture_planted_violations') }}
),

reported as (
    select distinct override_id, violation from {{ ref('rpt_control_violations') }}
)

select p.override_id, p.violation, 'planted but not reported' as problem
from planted p
left join reported r on r.override_id = p.override_id and r.violation = p.violation
where r.override_id is null

union all

select r.override_id, r.violation, 'reported but not planted'
from reported r
where r.override_id not in (select override_id from planted)
