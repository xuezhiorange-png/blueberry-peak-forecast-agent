# Q2D Historical Label Source Attestation Contract

> Issue: #102
> Round: V0_2_S2_Q2D_HISTORICAL_LABEL_SOURCE_ATTESTATION
> Status: design-only; no data collection, import, code, schema or backtest
> Base: `480f64cf093827dc7401ae9cdafe7b9f870bfd66`

## 1. Purpose and boundary

Q2D defines the business evidence required to prove that a historical source
can supply the Q2C actual-label boundary. It does not identify a real source,
request data, import rows, change forecast code, implement a backtest runner,
or authorize Q2B execution.

The frozen actual target remains:

```text
ACTUAL_PHYSICAL_EVENT=FARM_PICK
ACTUAL_QUANTITY_BASIS=OBSERVED_WEIGHT
ACTUAL_QUANTITY_UNIT=KG
ACTUAL_TIME_BASIS=FARM_LOCAL_HARVEST_BUSINESS_DATE
ACTUAL_MISSING_SEMANTICS=UNKNOWN_NOT_ZERO
ACTUAL_GRAIN=SEASON x FARM x SUBFARM_OR_PLOT x VARIETY x HARVEST_BUSINESS_DATE
```

The Q2C candidate `model_harvested_marketable_quantity_kg` remains unresolved.
Receipt, arrival, processing and retained-marketable quantities are not
accepted as FARM_PICK labels without a separately attested and versioned
transformation authority.

```text
Q2D_DESIGN_ONLY=true
PRODUCTION_CODE_CHANGED=false
TEST_CODE_CHANGED=false
MIGRATION_CHANGED=false
DATA_IMPORTED=false
BACKTEST_EXECUTED=false
Q2B_IMPLEMENTATION_AUTHORIZED=false
```

## 2. Decision status vocabulary

The Q2D final decision status is closed to exactly these values:

```text
BUSINESS_ATTESTATION_READY
BLOCKED_BY_MISSING_SOURCE_OWNER
BLOCKED_BY_MISSING_MEASUREMENT_BOUNDARY
BLOCKED_BY_MISSING_HISTORICAL_VISIBILITY
```

The current repository audit result is:

```text
Q2D_CURRENT_STATUS=BLOCKED_BY_MISSING_SOURCE_OWNER
```

No source owner, signed business attestation, measurement evidence or
historical visibility evidence is present in the checked-in repository. The
primary status names the first authority failure. The evidence matrix records
remaining independent gaps; none may be silently treated as passed.

## 3. Who may attest

The authoritative actor is a formally accountable `business_owner_role` or a
governed source-system authority for the specific source dataset and version.
The role must have responsibility for the physical weighing process and the
historical data publication policy. A developer, model owner, database
administrator, analyst, file uploader or person who merely knows the field name
is not sufficient unless source governance explicitly grants that role
authority.

Q2D does not invent the source owner. The owner must be identified from a
governed source registry, approved operating procedure, source-system ownership
record or equivalent auditable authority. A personal name is not required and
must not be copied into evaluation evidence.

```text
SOURCE_OWNER_AUTHORITY=FORMAL_BUSINESS_ROLE_OR_GOVERNED_SOURCE_SYSTEM
PERSONAL_DATA_REQUIRED=false
ROLE_OR_SYSTEM_AUTHORITY_ONLY=true
UNSIGNED_NARRATIVE_IS_NOT_AUTHORITY=true
FIELD_NAME_IS_NOT_ATTESTATION=true
DEVELOPER_OR_TEST_FIXTURE_IS_NOT_AUTHORITY=true
```

The authority chain is:

```text
source owner role
 -> governed source system and dataset
 -> versioned source snapshot
 -> signed/versioned business attestation
 -> immutable attestation hash
 -> Q2C equivalence decision
 -> Q2B readiness gate
```

If any link is missing, Q2B remains blocked.

## 4. Required source identity and lifecycle

The attestation must name the source exactly. It must not use `latest`,
`current`, a filename, an unversioned spreadsheet, an environment variable or
an inferred database table as the source identity.

```text
source_system=<stable governed source-system code>
source_dataset=<stable governed dataset or extract code>
source_version=<schema, snapshot, release or effective version>
source_snapshot_reference=<stable governed reference, not a private URL>
business_owner_role=<role or system authority>
attestation_effective_at=<timezone-aware timestamp>
attestation_version=<monotonic version within source identity>
attestation_status=DRAFT|ATTESTED|SUPERSEDED|REVOKED
```

`DRAFT`, `ATTESTED`, `SUPERSEDED` and `REVOKED` describe attestation
lifecycle, not Q2D decision status. Only an `ATTESTED` version effective for
the historical rows may support `BUSINESS_ATTESTATION_READY`.

An attestation is immutable after publication. A changed source policy,
measurement boundary, date rule or correction rule creates a new attestation
version; it must not rewrite the old version.

## 5. Physical and measurement boundary

The owner must answer all of the following for the named source version:

```text
physical_event=FARM_PICK|OTHER
weighing_point=FIELD_SCALE|HARVEST_CONTAINER|PACKHOUSE|FACTORY|OTHER
weighing_time_relative_to_pick=BEFORE|DURING|AFTER|UNKNOWN
weighing_time_description=<bounded business rule>
all_picked_or_marketable_only=ALL_PICKED|MARKETABLE_ONLY|UNKNOWN
rejected_fruit_included=TRUE|FALSE|UNKNOWN
field_sorting_before_weight=TRUE|FALSE|UNKNOWN
packhouse_sorting_before_weight=TRUE|FALSE|UNKNOWN
postharvest_loss_before_weight=TRUE|FALSE|UNKNOWN
postharvest_handling_before_weight=TRUE|FALSE|UNKNOWN
tare_policy=<versioned policy code or bounded description>
unit=KG|OTHER
measurement_method=<scale or measurement method code>
scale_calibration_authority=<role or system authority>
measurement_precision=<declared precision>
rounding_policy=<versioned Decimal/rounding rule>
```

For exact FARM_PICK equivalence, `physical_event` must be `FARM_PICK`, the
unit must be `KG`, the weighing boundary must be explicit relative to picking,
and marketability, sorting and post-harvest behavior must be known. `UNKNOWN`
is a blocker, not permission to choose a convenient interpretation.

The attestation must distinguish all fruit picked, marketable-only fruit,
field rejection, field sorting, packhouse sorting, transport/storage loss,
other post-harvest loss, and tare/container effects. A retention factor does
not prove this boundary; any conversion requires a separately versioned
transformation authority.

## 6. Date and grain authority

`harvest_business_date` must be assigned by a declared source policy, not by
UTC conversion, receipt date, insertion date, filename, year extraction or
correction date.

```text
harvest_business_date_assignment_policy=<versioned rule>
farm_timezone_authority=<versioned farm/timezone source>
day_boundary_policy=<versioned local-day rule>
late_entry_policy=<versioned rule>
missing_day_policy=UNKNOWN_NOT_ZERO|OTHER_EXPLICIT_POLICY
correction_date_policy=<versioned rule>
source_recorded_at_authority=<source-time field and meaning>
source_available_at_authority=<visibility field and meaning>
```

The source must expose or deterministically map season, farm, subfarm or plot,
variety, date and quantity at:

```text
SEASON x FARM x SUBFARM_OR_PLOT x VARIETY x HARVEST_BUSINESS_DATE
```

Mappings must be exact, case-sensitive or explicitly versioned. Fuzzy
matching, display-name fallback, latest/current lookup, insertion order,
filename inference and year inference are forbidden. A plot code must not be
silently interpreted as a subfarm code.

## 7. Revision and point-in-time authority

Historical labels must be append-only and revision-aware. The owner must
declare:

```text
logical_record_key=<stable source logical identity>
revision_key=<stable source revision identity>
revision_number_policy=<continuity and numbering rule>
predecessor_policy=<correction predecessor rule>
correction_policy=<effective and visibility rule>
void_policy=<how voided records remain auditable>
finalization_policy=<when a record is authoritative>
duplicate_policy=<same identity and same/different payload behavior>
visibility_authority=<source field/status and meaning>
visibility_timestamp=<recorded/committed/published timestamp>
publication_boundary=<versioned rule>
late_entry_visibility=<versioned rule>
correction_visibility=<versioned rule>
source_snapshot_cutoff_policy=<versioned rule>
```

The historical view must be reproducible at a forecast cutoff using an
immutable snapshot or visibility manifest. Current database state, current
mapping, latest revision, post-cutoff export and insertion order are not
historical visibility evidence.

## 8. Canonical attestation and acceptance

The canonical payload includes sections 4 through 7, coverage and exclusions:

```text
coverage_scope=<farms/seasons/date range/source partitions>
known_exclusions=<bounded canonical list>
attestation_hash=<SHA-256 over canonical attestation payload>
```

Canonicalization uses explicit enums, ISO timestamps/dates, exact Decimal
strings and stable business identities. Hashes exclude database IDs, runtime
timestamps, host names, credentials, insertion/query order and personal data.

`BUSINESS_ATTESTATION_READY` requires: an identified formal owner; exact source
identity; an effective immutable ATTESTED version; explicit FARM_PICK/observed
kg/unit and measurement boundaries; farm-local date and missing-day rules;
exact identity grain; revision authority; replayable historical visibility;
bounded scope/exclusions; and no hidden transformation.

The first failed authority determines the closed status:

| failed authority | decision status |
|---|---|
| owner role or source authority missing | `BLOCKED_BY_MISSING_SOURCE_OWNER` |
| weighing, sorting, marketability or post-harvest boundary missing | `BLOCKED_BY_MISSING_MEASUREMENT_BOUNDARY` |
| recorded/available/correction visibility cannot be reconstructed | `BLOCKED_BY_MISSING_HISTORICAL_VISIBILITY` |
| all required evidence is complete and attested | `BUSINESS_ATTESTATION_READY` |

## 9. Governance exclusions

```text
READY=NO
MERGE=NO
ISSUE102_CLOSE=NO
Q2B_IMPLEMENTATION=NOT_AUTHORIZED
BACKTEST_EXECUTION=NOT_AUTHORIZED
Q2D_DATA_COLLECTION=NOT_AUTHORIZED
Q2D_DATA_IMPORT=NOT_AUTHORIZED
NO_STEP_IMPLIES_THE_NEXT=true
```
