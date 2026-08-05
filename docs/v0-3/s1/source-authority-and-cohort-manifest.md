# S1 Source Authority and Cohort Manifest

## Purpose and current state

This contract defines the identity, scope, and custody of an approved source
cohort without including the cohort itself. It accepts a governed
source-system attestation or equivalent authority; a developer-selected table,
fixture, or file name is not sufficient.

```text
CURRENT_SOURCE_AUTHORITY_BINDING_STATUS=BLOCKED
CURRENT_SOURCE_COHORT_FREEZE_STATUS=BLOCKED
CURRENT_SOURCE_MANIFEST_STATUS=BLOCKED
CURRENT_SOURCE_OWNER_ROLE=NOT_PROVIDED
CURRENT_SOURCE_SYSTEM=NOT_PROVIDED
CURRENT_SOURCE_DATASET=NOT_PROVIDED
CURRENT_SOURCE_VERSION=NOT_PROVIDED
CURRENT_SOURCE_SNAPSHOT_REFERENCE=NOT_PROVIDED
CURRENT_SOURCE_COHORT_ID=NOT_ISSUED
```

The values above are explicit absence states. They are not placeholders for
approval and cannot be used as acceptance evidence.

## Source authority identity

An accepted source authority must bind all of the following fields in one
attestation version. `schema_version` is a logical schema identity and is not
interchangeable with the separately bound `schema_hash`. `effective_time` describes the source
authority's period of applicability and is not replaced by the attestation
signature time.

```text
REQUIRED_SOURCE_AUTHORITY_IDENTITY_FIELDS=
source_system,
source_dataset,
source_version,
schema_version,
schema_hash,
source_snapshot_reference,
source_owner_role,
attestation_version,
attestation_effective_at,
effective_time,
attestation_status,
attestation_hash,
coverage_scope,
revision_policy,
withdrawal_and_void_policy,
known_exclusions
```

`source_snapshot_reference` is an immutable, non-sensitive, governed opaque
identity. It must not be a private URL or plaintext storage path. When a
locator must be bound for custody, only `storage_locator_hash` may be recorded.

```text
effective_time=
  effective_from,
  effective_to_or_open_ended,
  authority_timezone

coverage_scope=
  seasons,
  farms,
  subfarms,
  varieties,
  business_date_start,
  business_date_end,
  known_scope_boundaries

revision_policy=
  revision_policy_version,
  revision_policy_identity,
  winner_and_lineage_rule

withdrawal_and_void_policy=
  withdrawal_policy_version,
  void_propagation_policy_version,
  withdrawal_status_rule,
  void_status_rule
```

`attestation_status` must be `ATTESTED` before an authority can be accepted.
`DRAFT`, `SUPERSEDED`, `REVOKED`, `UNSIGNED`, and inferred values are not
acceptable. The attestation hash covers the canonical attestation object,
excluding transport metadata and personal data.

## S1/S2 ownership boundary

S1 freezes the identity and policy references of the source cohort. S2 owns the
materialized cleaned rowset and all downstream split or snapshot rowsets.

```text
S1_FREEZES_SOURCE_COHORT_IDENTITY=true
S1_FREEZES_FINAL_CLEAN_ROWSET=false
S2_OWNS_FINAL_MATERIALIZED_ROWSET=true

SOURCE_ROW_COUNT_IS_DECLARED_SOURCE_METADATA=true
SOURCE_ROW_COUNT_IS_NOT_S2_ACCEPTED_ROW_COUNT=true
SOURCE_ROW_COUNT_DOES_NOT_FREEZE_FINAL_ROWSET=true
declared_source_row_count=NOT_PROVIDED
declared_source_byte_count=NOT_PROVIDED
```

Missing counts remain `NOT_PROVIDED`; they must not be represented as zero.
S1 does not use `accepted_row_count`, `cleaned_row_count`, or
`materialized_row_count` as source-cohort fields.

## Cohort manifest identity

The cohort manifest is an aggregate source identity and custody record. It must
not contain raw rows, cleaned rowsets, split rowsets, label snapshots, or
sensitive payloads. It binds:

```text
REQUIRED_COHORT_MANIFEST_FIELDS=
manifest_version,
cohort_id,
source_system,
source_dataset,
source_version,
schema_version,
schema_hash,
source_snapshot_reference,
source_owner_role,
attestation_version,
attestation_effective_at,
effective_time,
attestation_status,
attestation_hash,
coverage_scope,
revision_policy,
withdrawal_and_void_policy,
known_exclusions,
mapping_policy_version,
visibility_policy_version,
inclusion_policy_version,
revision_policy_version,
split_policy_version,
source_object_identity_hashes,
custody_record,
manifest_hash
```

Source object identity roles are references only:

```text
RAW_SOURCE_AUTHORITY_REFERENCE
SOURCE_OBJECT_REFERENCE
SOURCE_SCHEMA_REFERENCE
SOURCE_MAPPING_REFERENCE
```

The roles above do not represent `FINAL_CLEAN_ROWSET`, materialized dataset
partitions, split manifests, or label snapshots. Each reference is immutable,
versioned, and represented by a SHA-256 digest plus an opaque identity. A
source object cannot be replaced in place.

## Cohort coverage scope and exclusions

Coverage metadata is aggregate-only and must describe the applicable seasons,
farms, subfarms, varieties, business-date range, and known scope boundaries.
It may include declared source row and byte counts, but it does not establish
accepted, cleaned, or materialized row counts. It must also record known
exclusions and representativeness limits. A narrow cohort must not support a
global accuracy claim.

## Required physical semantics

The attestation and source cohort must bind the Q2C dimensions:

```text
REQUIRED_PHYSICAL_EVENT=FARM_PICK
REQUIRED_QUANTITY_BASIS=OBSERVED_WEIGHT
REQUIRED_QUANTITY_UNIT=KG
REQUIRED_TIME_BASIS=FARM_LOCAL_HARVEST_BUSINESS_DATE
REQUIRED_MISSING_SEMANTICS=UNKNOWN_NOT_ZERO
REQUIRED_GRAIN=SEASON × FARM × SUBFARM × VARIETY × HARVEST_BUSINESS_DATE
PLOT_SUPPORTED=false
```

The physical measurement record must state the weighing point and its relation
to picking, whether all picked fruit or marketable fruit is weighed, field and
packhouse sorting/rejection rules, transport/storage/post-harvest loss, tare,
scale precision/calibration authority, Decimal precision/rounding, farm
timezone, local day boundary, delayed entry, correction, void, finalization,
and historical visibility.

## Mapping and revision identity

The manifest must freeze the mapping policy used to resolve farm, subfarm,
variety, season, and business date. A live master-data remap after freeze is
not evidence. Mapping evidence is a versioned object with a schema/policy hash
and deterministic identity.

Revision identity must preserve source record identity, revision number,
superseded parent, status, source-recorded time, source availability time,
source revision time, finalized time where required, cancellation time where
required, and source-system scope. The winner is computed by the Q2A/I7 lineage
rules; it is never selected by largest quantity, latest import, database order,
or lexical hash.

## Hash and custody rules

```text
HASH_ALGORITHM=SHA-256
CANONICALIZATION=VERSIONED_CANONICAL_JSON_WITH_DECIMAL_STRINGS
RAW_SOURCE_IMMUTABLE=true
CLEANED_DATA_VERSIONED=true
MANUAL_CORRECTION_AUDITED=true
SILENT_VALUE_REPLACEMENT=false
SOURCE_ROW_LINEAGE_REQUIRED=true
POINT_IN_TIME_VISIBILITY_REQUIRED=true
REAL_DATA_ALLOWED_IN_GIT=false
```

The source object, schema, mapping, visibility, inclusion, split, attestation,
and final manifest each have a distinct identity. A ZIP digest, a checksum
manifest digest, and a source-object digest must never be used
interchangeably.

The versioned custody record must bind:

```text
CUSTODY_RECORD_FIELDS=
custody_policy_version,
storage_type,
access_owner_role,
source_owner_role,
approved_usage_purpose,
least_privilege_scope,
authorized_role_set,
credential_reference_policy,
retention_policy_version,
retention_period_or_rule,
withdrawal_policy_version,
void_propagation_policy_version,
downstream_propagation_targets,
external_object_binding_hash,
custody_record_hash
```

The record contains policy identities and non-sensitive hashes only. It does
not contain credentials, tokens, private URLs, plaintext storage locators, or
personal identity.

## Withdrawal and void propagation

Source withdrawal must not silently delete prior evidence. It creates a new
versioned custody/status record. A withdrawn or void source identity must be
propagated to the source cohort, any future split manifest, any future label
snapshot manifest, and the acceptance record. Every affected unfinished gate
becomes `BLOCKED`; accepted artifacts are never rewritten in place. A
replacement source creates a new identity and new hashes. Only non-sensitive
hashes and policy identities may be retained in Git.

## Current blockers and acceptance requirements

```text
CURRENT_SOURCE_AUTHORITY_BINDING_STATUS=BLOCKED
CURRENT_SOURCE_COHORT_FREEZE_STATUS=BLOCKED
CURRENT_SOURCE_ATTESTATION_STATUS=BLOCKED_BY_MISSING_BUSINESS_ATTESTATION
S1_ACCEPTANCE_REQUIRES_ATTESTATION_STATUS_ATTESTED=true
S1_ACCEPTANCE_REQUIRES_IMMUTABLE_SOURCE_VERSION=true
S1_ACCEPTANCE_REQUIRES_SCHEMA_VERSION=true
S1_ACCEPTANCE_REQUIRES_EFFECTIVE_TIME=true
S1_ACCEPTANCE_REQUIRES_COVERAGE_SCOPE=true
S1_ACCEPTANCE_REQUIRES_WITHDRAWAL_AND_VOID_POLICY=true
S1_ACCEPTANCE_REQUIRES_SOURCE_OBJECT_HASHES=true
S1_ACCEPTANCE_REQUIRES_COHORT_MANIFEST_HASH=true
S1_ACCEPTANCE_REQUIRES_LINEAGE_AND_MAPPING_EVIDENCE=true
S1_ACCEPTANCE_REQUIRES_CUSTODY_RECORD=true
```

No source value, owner identity, cohort identity, manifest hash, or acceptance
result is issued by this document.
