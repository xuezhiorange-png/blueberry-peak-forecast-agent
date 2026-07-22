# Q2F Attestation Intake Template

This file is a canonical intake shape only. It contains no business attestation
and no invented positive value.

```text
ATTESTATION_STATUS_VALUES=DRAFT|ATTESTED|SUPERSEDED|REVOKED
POSITIVE_GATE_VALUE=ATTESTED
CANONICAL_ENCODING=UTF-8
CANONICAL_JSON_KEYS=SORTED
TIMESTAMP_FORMAT=RFC3339_WITH_TIMEZONE
HASH_ALGORITHM=SHA-256
```

## Canonical JSON template

The following template must be filled only from a separately approved,
reviewable governed artifact. `DRAFT` is non-acceptance; `UNRESOLVED` and
`NONE` are placeholders and must not be treated as evidence.

```json
{
  "attestation_effective_at": "UNRESOLVED",
  "attestation_status": "DRAFT",
  "attestation_version": "UNRESOLVED",
  "business_owner_role": "UNRESOLVED",
  "date_and_grain": {
    "canonical_grain_policy": "UNRESOLVED",
    "correction_date_policy": "UNRESOLVED",
    "day_boundary_policy": "UNRESOLVED",
    "farm_timezone_authority": "UNRESOLVED",
    "harvest_business_date_assignment_policy": "UNRESOLVED",
    "late_entry_policy": "UNRESOLVED",
    "missing_day_policy": "UNRESOLVED",
    "season_identity_policy": "UNRESOLVED",
    "farm_identity_policy": "UNRESOLVED",
    "subfarm_or_plot_identity_policy": "UNRESOLVED",
    "variety_identity_policy": "UNRESOLVED"
  },
  "frozen_target": {
    "actual_grain": "SEASON x FARM x SUBFARM_OR_PLOT x VARIETY x HARVEST_BUSINESS_DATE",
    "actual_physical_event": "FARM_PICK",
    "actual_quantity_basis": "OBSERVED_WEIGHT",
    "actual_quantity_unit": "KG",
    "actual_time_basis": "FARM_LOCAL_HARVEST_BUSINESS_DATE",
    "actual_missing_semantics": "UNKNOWN_NOT_ZERO"
  },
  "measurement": {
    "all_picked_or_marketable_only": "UNRESOLVED",
    "field_sorting_before_weight": "UNRESOLVED",
    "measurement_method": "UNRESOLVED",
    "measurement_precision": "UNRESOLVED",
    "packhouse_sorting_before_weight": "UNRESOLVED",
    "physical_event": "UNRESOLVED",
    "postharvest_handling_before_weight": "UNRESOLVED",
    "postharvest_loss_before_weight": "UNRESOLVED",
    "rejected_fruit_included": "UNRESOLVED",
    "rounding_policy": "UNRESOLVED",
    "scale_calibration_authority": "UNRESOLVED",
    "tare_policy": "UNRESOLVED",
    "unit": "UNRESOLVED",
    "weighing_point": "UNRESOLVED",
    "weighing_time_relative_to_pick": "UNRESOLVED"
  },
  "revision": {
    "correction_policy": "UNRESOLVED",
    "finalization_policy": "UNRESOLVED",
    "logical_record_key": "UNRESOLVED",
    "predecessor_policy": "UNRESOLVED",
    "revision_key": "UNRESOLVED",
    "revision_number_policy": "UNRESOLVED",
    "void_policy": "UNRESOLVED"
  },
  "source": {
    "source_dataset": "UNRESOLVED",
    "source_snapshot_reference": "NONE",
    "source_system": "UNRESOLVED",
    "source_version": "UNRESOLVED"
  },
  "visibility": {
    "correction_visibility": "UNRESOLVED",
    "historical_snapshot_or_manifest": "NONE",
    "late_entry_visibility": "UNRESOLVED",
    "publication_boundary": "UNRESOLVED",
    "visibility_timestamp": "UNRESOLVED"
  },
  "hashes": {
    "attestation_payload_sha256": "NONE",
    "historical_visibility_manifest_sha256": "NONE",
    "source_release_manifest_sha256": "NONE"
  }
}
```

## Canonicalization rules

- Encode the final JSON as UTF-8.
- Serialize object keys in sorted order and preserve the documented field names.
- Use RFC3339 timestamps with an explicit timezone only when supplied by the
  governed artifact.
- Use SHA-256 only for a completed, non-placeholder canonical artifact.
- Do not calculate or publish a hash over this placeholder template as a
  business attestation.
- Do not include comments, personal data, credentials, private URLs, raw rows,
  database IDs, or mutable current/latest lookups.

Until a real governed artifact exists, the intake remains:

```text
ATTESTATION_STATUS=NOT_ATTESTED
ATTESTATION_PAYLOAD_SHA256=NONE
BUSINESS_ATTESTATION_READY=false
```
