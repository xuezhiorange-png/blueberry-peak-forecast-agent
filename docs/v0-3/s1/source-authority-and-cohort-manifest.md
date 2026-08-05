# S1 Source Authority and Cohort Manifest

## Purpose and current state

This contract defines the identity and custody of an approved source cohort
without including the cohort itself. It accepts a governed source-system
attestation or equivalent authority; a developer-selected table, fixture, or
file name is not sufficient.

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

## Required authority identity

An accepted source authority must bind all fields below in one attestation
version. A role or governed system identity is required; personal names,
emails, phone numbers, access tokens, credentials, and private URLs are not
stored in this repository.

```text
REQUIRED_SOURCE_IDENTITY_FIELDS=
source_system,
source_dataset,
source_version,
source_snapshot_reference,
source_owner_role,
attestation_version,
attestation_effective_at,
attestation_status,
attestation_hash
```

`attestation_status` must be `ATTESTED`. `DRAFT`, `SUPERSEDED`, `REVOKED`,
`UNSIGNED`, and inferred values are not acceptable. The hash covers the
canonical attestation object, excluding transport metadata and personal data.

## Cohort manifest identity

The cohort manifest is an aggregate identity and custody record. It must not
contain raw rows or sensitive payloads. It binds:

```text
REQUIRED_COHORT_MANIFEST_FIELDS=
manifest_version,
cohort_id,
source_system,
source_dataset,
source_version,
source_snapshot_reference,
attestation_hash,
schema_hash,
mapping_policy_version,
visibility_policy_version,
inclusion_policy_version,
revision_policy_version,
split_policy_version,
coverage_summary,
exclusion_summary,
source_object_identity_hashes,
manifest_hash
```

The same field names are used in the JSON schema without any presentation
markers.

Each source object identity is represented by a SHA-256 digest and immutable
version/reference metadata, not by a live private location. The manifest must
also record whether the object is the raw source, a governed cleaned version,
or a split artifact. A source object cannot be replaced in place.

## Cohort coverage summary

The summary is aggregate-only and must include:

- season set and farm/subfarm/variety identity counts;
- first and last farm-local harvest business dates;
- source row count and accepted row count;
- excluded row count by reason code;
- missing business-date count and missing-data proportion;
- source and target units;
- explicit known exclusions and representativeness limits.

The summary does not establish representativeness by itself. A narrow cohort
must not support a global accuracy claim.

## Required source semantics

The attestation and manifest must bind the Q2C dimensions:

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
superseded parent, status, source-recorded time, finalized time where required,
and the source system scope. The winner is computed by the Q2A/I7 lineage rules;
it is never selected by largest quantity, latest import, database order, or
lexical hash.

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
manifest digest, and a source-object digest must never be used interchangeably.

## Current blockers and acceptance requirements

```text
CURRENT_SOURCE_AUTHORITY_BINDING_STATUS=BLOCKED
CURRENT_SOURCE_COHORT_FREEZE_STATUS=BLOCKED
CURRENT_SOURCE_ATTESTATION_STATUS=BLOCKED_BY_MISSING_BUSINESS_ATTESTATION
S1_ACCEPTANCE_REQUIRES_ATTESTATION_STATUS_ATTESTED=true
S1_ACCEPTANCE_REQUIRES_IMMUTABLE_SOURCE_VERSION=true
S1_ACCEPTANCE_REQUIRES_SOURCE_OBJECT_HASHES=true
S1_ACCEPTANCE_REQUIRES_COHORT_MANIFEST_HASH=true
S1_ACCEPTANCE_REQUIRES_LINEAGE_AND_MAPPING_EVIDENCE=true
S1_ACCEPTANCE_REQUIRES_CUSTODY_RECORD=true
```

No source value, cohort identity, or manifest hash is issued by this document.
