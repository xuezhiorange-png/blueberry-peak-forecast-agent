# Q2F Business Source Evidence Intake Decision

```text
Q2F_BUSINESS_SOURCE_EVIDENCE_INTAKE_COMPLETE=true
Q2F_CURRENT_STATUS=EVIDENCE_REQUEST_PACKAGE_READY
BASE_SHA=b05a05396535a42bf52f26d965af2468e424694f
```

`EVIDENCE_REQUEST_PACKAGE_READY` means only that a bounded request package is
ready to send to a formal business role or governed source-system authority. It
does not mean that the source, physical label, or forecast target is verified.

## Evidence status

```text
SOURCE_OWNER_IDENTIFIED=NO
SOURCE_SYSTEM_IDENTIFIED=NO
SOURCE_DATASET_IDENTIFIED=NO
SOURCE_VERSION_IDENTIFIED=NO
MEASUREMENT_BOUNDARY_VERIFIED=NO
DATE_AND_GRAIN_AUTHORITY_VERIFIED=NO
REVISION_AUTHORITY_VERIFIED=NO
HISTORICAL_VISIBILITY_VERIFIED=NO
PHYSICAL_TARGET_EQUIVALENCE_VERIFIED=NO

ATTESTATION_STATUS=NOT_ATTESTED
BUSINESS_ATTESTATION_READY=false
ATTESTATION_PAYLOAD_SHA256=NONE
```

The frozen actual-label target remains:

```text
ACTUAL_PHYSICAL_EVENT=FARM_PICK
ACTUAL_QUANTITY_BASIS=OBSERVED_WEIGHT
ACTUAL_QUANTITY_UNIT=KG
ACTUAL_TIME_BASIS=FARM_LOCAL_HARVEST_BUSINESS_DATE
ACTUAL_MISSING_SEMANTICS=UNKNOWN_NOT_ZERO
ACTUAL_GRAIN=SEASON x FARM x SUBFARM_OR_PLOT x VARIETY x HARVEST_BUSINESS_DATE
```

No source owner is inferred from Git identity, PR authorship, database users,
file or table names, field names, fixtures, developer statements, or general
organization knowledge. No raw business rows, personal data, credentials, or
private links are requested or stored.

## Release condition

```text
NEXT_RELEASE_CONDITION=VERSIONED_ATTESTED_EVIDENCE_SUPPLIED_BY_FORMAL_ROLE_OR_GOVERNED_AUTHORITY
```

The supplied artifact must cover source identity and release version, physical
measurement boundaries, farm-local date and canonical grain, revision policy,
publication boundary, visibility timestamp, and an immutable historical
snapshot or manifest. A positive status requires `ATTESTATION_STATUS=ATTESTED`.

## Authorization boundary

```text
Q2B_IMPLEMENTATION_AUTHORIZED=false
BACKTEST_EXECUTION_AUTHORIZED=false
DATA_COLLECTION_AUTHORIZED=false
DATA_IMPORT_AUTHORIZED=false
PRODUCTION_CODE_CHANGED=false
TEST_CODE_CHANGED=false
SCHEMA_CHANGED=false
MIGRATION_CHANGED=false
READY=false
MERGE=false
ISSUE102_CLOSE=false
NO_STEP_IMPLIES_THE_NEXT=true
```

Q2F does not authorize data collection, data import, Q2B implementation,
backtest execution, model or parameter changes, schema or migration changes,
Ready, Merge, Issue closure, branch deletion, or worktree cleanup.
