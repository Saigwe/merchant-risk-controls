-- Approved overrides need a checker who is not the proposer.
select *
from {{ ref('stg_bronze__overrides') }}
where status = 'approved'
  and (approved_by is null or approved_by = proposed_by)
