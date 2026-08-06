# V0.3-S1 Season Calendar Rule Draft

## Workpaper identity and status

```text
WORKPAPER_ID=V0_3_S1_SEASON_CALENDAR_RULE_DRAFT
BASE_MAIN_SHA=91fff1fb976cfdbbdc59807537e40dde37364b75
WORKPAPER_STATUS=DRAFT_ONLY
SEASON_CALENDAR_BUSINESS_RULE_STATUS=CONFIRMED
SOURCE_SNAPSHOT_METADATA_STATUS=PENDING
SOURCE_SNAPSHOT_METADATA_ENTRY_MODE=MACHINE_GENERATED
MANUAL_BUSINESS_USER_ENTRY_REQUIRED=false

CURRENT_Q2C_PHYSICAL_ALIGNMENT_STATUS=BLOCKED
CURRENT_SOURCE_AUTHORITY_BINDING_STATUS=BLOCKED
CURRENT_SOURCE_COHORT_FREEZE_STATUS=BLOCKED
CURRENT_V0_3_S1_COMPLETE=false
CURRENT_V0_3_S1_ACCEPTANCE_STATUS=BLOCKED
V0_3_S1_ACCEPTED=false
V0_3_S2_AUTHORIZED=false
V0_3_S2_STARTED=false
```

This workpaper freezes only the confirmed business calendar rule for later
source-to-season mapping. It is not a source snapshot, a cohort manifest, a
Q2C decision, or a formal acceptance record.

## Confirmed cross-year season rule

```text
SEASON_START_MONTH_DAY=08-01
SEASON_END_MONTH_DAY=06-30
BOUNDARY_INCLUSIVITY=起止日期均包含
SEASON_START_YEAR=产季名称中的前一年
SEASON_END_YEAR=产季名称中的后一年
```

The rule maps a season name written as `YYYY~YYYY` to August 1 of the first
year through June 30 of the second year, inclusive. Subsequent seasons follow
the same cross-year rule.

```text
2024~2025产季=2024-08-01至2025-06-30
2025~2026产季=2025-08-01至2026-06-30
```

## July boundary and unresolved exception handling

```text
JULY_AUTOMATIC_SEASON_ASSIGNMENT=false
UNMAPPED_DATE_POLICY=PENDING
```

July is outside the automatic assignment range. This draft does not decide
whether July belongs to the previous season or the following season, whether
it is automatically excluded, how overlapping dates are prioritized, or how an
exception date is corrected. Those decisions require separately authorized
business and system evidence.

## Source-snapshot metadata boundary

Source export time, file name or export ID, file hash, row count, date bounds,
coverage counts, and missing-day count are not read or generated here. A later
authorized machine-generated snapshot step will calculate those metadata fields
from a governed export; no manual business-user entry is required.

## Authorization boundary

```text
Q2C_DECISION_HASH=NOT_ISSUED
SOURCE_SNAPSHOT_REFERENCE=NOT_ISSUED
ATTESTATION_HASH=NOT_ISSUED
REAL_BUSINESS_ROW_LEVEL_DATA_READ=false
REAL_BUSINESS_ROW_LEVEL_DATA_IMPORTED=false
SOURCE_EXPORT_FILE_READ=false
SOURCE_HASH_CALCULATION=false
TEST_DATA_ACCESSED=false
EXTERNAL_HOLDOUT_DATA_ACCESSED=false
V0_3_S2_AUTHORIZED=false
V0_3_S2_STARTED=false
```

The calendar rule is a confirmed draft business rule only. It does not change
the formal S1 blocked statuses or authorize S1 acceptance or S2 ingestion.
