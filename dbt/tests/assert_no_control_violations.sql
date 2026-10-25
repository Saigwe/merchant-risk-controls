-- The audit claim: no event in the override log breaks a workflow control.
-- (Disabled for the CI fixture, which plants violations on purpose; see assert_planted_violations_detected.)
{{ config(enabled=not var('is_fixture', false)) }}
select * from {{ ref('rpt_control_violations') }}
