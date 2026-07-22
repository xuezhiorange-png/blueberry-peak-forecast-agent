# Q2F Business Source Evidence Request

```text
Q2F_EVIDENCE_REQUEST_PACKAGE=true
FORMAL_ROLE_OR_GOVERNED_AUTHORITY_REQUIRED=true
PERSONAL_IDENTITY_REQUIRED=false
RAW_BUSINESS_ROWS_REQUIRED=false
PRIVATE_SOURCE_ACCESS_REQUIRED=false
OWNER_INFERENCE_FORBIDDEN=true
```

## 1. Purpose and frozen target

This is a bounded request for governance evidence for the historical actual
label used by forecast-quality evaluation. It is not a request for raw rows,
credentials, database access, or a production import.

```text
ACTUAL_PHYSICAL_EVENT=FARM_PICK
ACTUAL_QUANTITY_BASIS=OBSERVED_WEIGHT
ACTUAL_QUANTITY_UNIT=KG
ACTUAL_TIME_BASIS=FARM_LOCAL_HARVEST_BUSINESS_DATE
ACTUAL_MISSING_SEMANTICS=UNKNOWN_NOT_ZERO
ACTUAL_GRAIN=SEASON x FARM x SUBFARM_OR_PLOT x VARIETY x HARVEST_BUSINESS_DATE
FORECAST_TARGET_CANDIDATE=model_harvested_marketable_quantity_kg
```

The requested authority is a stable formal business role code or governed
source-system authority code. A personal name is neither required nor wanted.

## 2. Source authority evidence requested

Provide, in a separately approved and reviewable artifact:

```text
business_owner_role
source_system
source_dataset
source_version
source_snapshot_reference
attestation_version
attestation_effective_at
attestation_status
```

The source release must be immutable or independently traceable. The positive
status is `ATTESTED`; a draft, superseded, revoked, unresolved, or unsigned
description is not sufficient.

## 3. Physical measurement evidence requested

For the specific source version, state and reference evidence for:

```text
physical_event
weighing_point
weighing_time_relative_to_pick
all_picked_or_marketable_only
rejected_fruit_included
field_sorting_before_weight
packhouse_sorting_before_weight
postharvest_loss_before_weight
postharvest_handling_before_weight
tare_policy
unit
measurement_method
scale_calibration_authority
measurement_precision
rounding_policy
```

The evidence must explicitly establish whether the quantity is all picked fruit
or marketable-only fruit. It must identify the boundary of field sorting,
packhouse sorting, rejection, loss, postharvest handling, tare, and rounding.

## 4. Date, identity, and grain evidence requested

State the versioned authority for:

```text
farm_timezone_authority
harvest_business_date_assignment_policy
day_boundary_policy
late_entry_policy
missing_day_policy
correction_date_policy
season_identity_policy
farm_identity_policy
subfarm_or_plot_identity_policy
variety_identity_policy
canonical_grain_policy
```

The missing-day rule must be explicit. The frozen default is
`missing_day_policy=UNKNOWN_NOT_ZERO`; a missing row must not be silently
converted to a zero quantity.

## 5. Revision and historical visibility evidence requested

State the authority and version for:

```text
logical_record_key
revision_key
revision_number_policy
predecessor_policy
correction_policy
void_policy
finalization_policy
publication_boundary
visibility_timestamp
late_entry_visibility
correction_visibility
historical_snapshot_or_manifest
```

The evidence must allow reconstruction of what was visible at a prediction
cutoff. Current/latest rows, insertion order, upload time, mutable shared files,
post-cutoff corrections, or current mapping tables are not historical visibility
evidence.

## 6. Bounded response checklist

Return only the following governance metadata and stable evidence references in
the separately approved artifact:

- formal role or governed authority code;
- source system, dataset, version, and immutable snapshot/release reference;
- attestation version, effective time, and status;
- measurement boundary and measurement-method references;
- timezone/date/grain policy references;
- revision and correction policy references;
- publication and historical-visibility manifest references;
- evidence gaps, conflicts, superseded versions, and revocation state.

Do not return:

- personal names, email addresses, phone numbers, or other personal data;
- credentials, tokens, cookies, or private URLs;
- raw business rows or full source files;
- database dumps, direct database access, or unbounded exports;
- inferred ownership based on Git authors, PR authors, database users, table or
  field names, filenames, test fixtures, developer statements, or organization
  guesses.

## 7. Acceptance boundary

An evidence request response does not verify the label by itself. Q2F remains
`EVIDENCE_REQUEST_PACKAGE_READY` until a formal role or governed source-system
authority supplies a versioned artifact whose status is `ATTESTED`. Until then,
Q2B implementation and backtest execution remain unauthorized.
