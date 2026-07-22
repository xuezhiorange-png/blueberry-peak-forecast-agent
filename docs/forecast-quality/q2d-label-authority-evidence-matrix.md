# Q2D Historical Label Authority Evidence Matrix

> Issue: #102
> Round: V0_2_S2_Q2D_HISTORICAL_LABEL_SOURCE_ATTESTATION
> Audit type: repository contract and evidence design only
> Base: `480f64cf093827dc7401ae9cdafe7b9f870bfd66`

## 1. Current decision

This matrix records what must be proven before Q2C can release the Q2B
physical-target blocker. It does not claim that any external source, owner or
historical row exists.

```text
Q2D_CURRENT_STATUS=BLOCKED_BY_MISSING_SOURCE_OWNER
BUSINESS_SOURCE_ATTESTATION=NOT_AVAILABLE
ACTUAL_LABEL_STATUS=UNVERIFIED
BACKTEST_AUTHORITY=BLOCKED
```

The only accepted actual-label boundary is:

```text
FARM_PICK / OBSERVED_WEIGHT / KG /
FARM_LOCAL_HARVEST_BUSINESS_DATE /
SEASON x FARM x SUBFARM_OR_PLOT x VARIETY x HARVEST_BUSINESS_DATE
```

## 2. Evidence state vocabulary

These are evidence-recording states, not final Q2D decision statuses:

```text
MISSING
PRESENT_UNVERIFIED
PRESENT_CONFLICTING
PRESENT_VERIFIED
NOT_APPLICABLE_WITH_ATTESTATION
```

The final decision remains restricted to `BUSINESS_ATTESTATION_READY`,
`BLOCKED_BY_MISSING_SOURCE_OWNER`,
`BLOCKED_BY_MISSING_MEASUREMENT_BOUNDARY`, and
`BLOCKED_BY_MISSING_HISTORICAL_VISIBILITY`.

## 3. Evidence matrix

| authority dimension | required evidence | authoritative source artifact | acceptance test | current state |
|---|---|---|---|---|
| source owner | formal accountable role or governed system authority | source registry, operating procedure or ownership record | role has authority for named dataset/version | MISSING |
| source identity | exact `source_system`, `source_dataset`, `source_version` | governed source catalog | identity is stable and versioned | MISSING |
| attestation lifecycle | effective `ATTESTED` version and supersession/revocation rule | attestation registry | version is immutable and effective for rows | MISSING |
| physical event | `FARM_PICK`, not arrival/receipt/processing | business process authority | owner explicitly attests event boundary | MISSING |
| weighing point | field, container, packhouse or factory point | scale/process authority | point is named and relation to pick is bounded | MISSING |
| weighing timing | before/during/after pick with bounded rule | measurement procedure | timing cannot be inferred from date or filename | MISSING |
| quantity population | all picked or marketable-only | measurement procedure | inclusion population is explicit | MISSING |
| rejected fruit | rejected/voided fruit inclusion rule | sorting/rejection procedure | rejection semantics are explicit | MISSING |
| field sorting | sorting before or after weight | field operation procedure | boundary and excluded quantity are known | MISSING |
| packhouse sorting | sorting before or after weight | packhouse procedure | boundary and excluded quantity are known | MISSING |
| post-harvest loss | handling, storage, transport and loss before weight | post-harvest procedure | loss boundary is explicit | MISSING |
| tare and unit | tare policy, KG unit, precision and rounding | scale procedure | exact Decimal conversion is reproducible | MISSING |
| calibration | calibration authority and effective policy | scale governance record | measurement reliability authority is named | MISSING |
| farm-local date | farm timezone and local-day rule | timezone/master-data authority | date is not inferred from UTC or receipt date | MISSING |
| late entry | delayed entry visibility rule | source publication procedure | late entry is visible only under declared rule | MISSING |
| missing day | `UNKNOWN_NOT_ZERO` or explicit governed alternative | source coverage procedure | absent row cannot become zero silently | MISSING |
| source identity grain | season, farm, subfarm/plot, variety and date keys | source schema and mapping authority | exact case-sensitive/versioned mapping | MISSING |
| plot boundary | explicit SUBFARM or PLOT target type | mapping authority | plot is never implicit subfarm | MISSING |
| season | source season code or deterministic date resolution | season master authority | unique and date-valid resolution | MISSING |
| revision key | logical and revision identity | source lineage procedure | same identity conflicts are fail-closed | MISSING |
| predecessor | correction predecessor and successor rules | source lineage procedure | graph is reconstructable without overwrite | MISSING |
| finalization | finalized/void/corrected status semantics | source workflow authority | winner authority is explicit and versioned | MISSING |
| source visibility | recorded, committed or published time | source event/audit log | visibility at historical cutoff is reproducible | MISSING |
| correction visibility | correction effective and available time | correction audit log | post-cutoff correction cannot rewrite prior view | MISSING |
| historical snapshot | immutable export or visibility manifest | source snapshot authority | exact source version can be replayed | MISSING |
| coverage | farms, seasons, date range and partitions | source owner attestation | scope is bounded and hashable | MISSING |
| exclusions | known missing farms, days, varieties and processes | source owner attestation | exclusions are explicit and maskable | MISSING |
| attestation hash | canonical payload hash | attestation registry | same payload same hash; changes new version | MISSING |
| Q2C binding | actual source boundary vs forecast candidate | Q2C evidence record | no unapproved transformation or proxy | MISSING |

## 4. Source candidate audit

No source owner or external historical dataset is identified by this design.
The following are repository-side contracts or candidate classes only; none is
accepted as real business evidence:

| candidate | repository meaning | Q2D disposition |
|---|---|---|
| Q2A actual-harvest import contract | accepts FARM_PICK/OBSERVED_WEIGHT/KG records | path exists; owner not verified |
| I7 immutable label snapshot | stores committed actual evidence | path exists; historical rows not verified |
| `model_harvested_marketable_quantity_kg` | model forecast candidate | not actual evidence; attestation required |
| `effective_marketable_quantity_kg` | post-sorting/post-harvest output | not FARM_PICK by default |
| `FactReceiptDaily.weight_kg` | factory receipt/arrival | forbidden primary label |
| tests and fixtures | synthetic or contract evidence | never business authority |

## 5. Required attestation payload

The source owner must provide a canonical, versioned payload with at least:

```text
source_system
source_dataset
source_version
business_owner_role
attestation_effective_at
attestation_version
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
harvest_business_date_assignment_policy
farm_timezone_authority
late_entry_policy
missing_day_policy
correction_and_revision_policy
visibility_authority
visibility_timestamp
correction_visibility_policy
coverage_scope
known_exclusions
attestation_hash
```

Canonicalization uses explicit enums, ISO timestamps/dates, exact Decimal
strings and stable business identities. Hashes exclude database IDs,
credentials, host data, query order, insertion order and personal data.

## 6. Gate evaluation

| gate | pass condition | failure decision |
|---|---|---|
| owner gate | formal source owner role/system authority identified | `BLOCKED_BY_MISSING_SOURCE_OWNER` |
| measurement gate | event, weighing, population, sorting and post-harvest boundaries explicit | `BLOCKED_BY_MISSING_MEASUREMENT_BOUNDARY` |
| identity/date gate | exact grain and farm-local date authority versioned | `BLOCKED_BY_MISSING_MEASUREMENT_BOUNDARY` |
| revision gate | correction, void, predecessor and finalization reconstructable | `BLOCKED_BY_MISSING_HISTORICAL_VISIBILITY` |
| visibility gate | snapshot and availability/correction timestamps support AS-OF | `BLOCKED_BY_MISSING_HISTORICAL_VISIBILITY` |
| hash gate | attestation immutable and hash-verifiable | `BLOCKED_BY_MISSING_SOURCE_OWNER` |
| target gate | forecast candidate physically equivalent without hidden transform | `BLOCKED_BY_MISSING_MEASUREMENT_BOUNDARY` |
| final gate | every required gate passes for requested scope | `BUSINESS_ATTESTATION_READY` |

The first failed gate is reported, but all unresolved rows remain open. A
later gate cannot compensate for a missing earlier authority.

## 7. Evidence that must not be accepted

```text
FIELD_NAME_AS_SEMANTICS=false
UNSIGNED_NARRATIVE_AS_AUTHORITY=false
RECEIPT_AS_FARM_PICK=false
ARRIVAL_AS_FARM_PICK=false
MODEL_OUTPUT_AS_OBSERVED_WEIGHT=false
CURRENT_ROW_AS_HISTORICAL_SNAPSHOT=false
LATEST_OR_CURRENT_FALLBACK=false
FILENAME_DATE_INFERENCE=false
UTC_YEAR_DATE_INFERENCE=false
INSERTION_ORDER_IDENTITY=false
FUZZY_MAPPING=false
FIXTURE_AS_BUSINESS_EVIDENCE=false
```

## 8. Frozen Q2D result

```text
Q2D_CURRENT_STATUS=BLOCKED_BY_MISSING_SOURCE_OWNER
ACTUAL_LABEL_STATUS=UNVERIFIED
BACKTEST_AUTHORITY=BLOCKED
Q2B_IMPLEMENTATION_READINESS=BLOCKED
```

The result may become `BUSINESS_ATTESTATION_READY` only after the missing
authority and all matrix rows are independently evidenced. Q2D does not
collect or import that evidence.
