# Q2E Historical Label Source Attestation Audit

```text
Q2E_ROUND=V0_2_S2_Q2E_BUSINESS_SOURCE_ATTESTATION
BASE_SHA=2e23441dade69fcdc74a64f2eccd220d40db5f27
Q2E_CURRENT_STATUS=BLOCKED_BY_MISSING_SOURCE_OWNER
BUSINESS_ATTESTATION_READY=false
```

## 1. Scope

This audit determines whether an authorized business role or governed source
system can attest, in a versioned and reviewable form, to the physical source
and historical visibility of the actual label used by the forecast-quality
backtest. It does not collect or export raw business rows, inspect credentials,
import data, run a backtest, change production code, or change the schema.

The frozen target under review is:

```text
ACTUAL_PHYSICAL_EVENT=FARM_PICK
ACTUAL_QUANTITY_BASIS=OBSERVED_WEIGHT
ACTUAL_QUANTITY_UNIT=KG
ACTUAL_TIME_BASIS=FARM_LOCAL_HARVEST_BUSINESS_DATE
ACTUAL_MISSING_SEMANTICS=UNKNOWN_NOT_ZERO
ACTUAL_GRAIN=SEASON x FARM x SUBFARM_OR_PLOT x VARIETY x HARVEST_BUSINESS_DATE
FORECAST_TARGET_CANDIDATE=model_harvested_marketable_quantity_kg
```

## 2. Sources inspected

The following repository and governance sources were inspected at the
authorized base. They define required evidence and software contracts; they
are not themselves a business attestation.

| Stable reference | Evidence obtained | Authority limitation |
|---|---|---|
| `docs/forecast-quality/q2d-historical-label-source-attestation-contract.md` | Defines owner, measurement, date/grain, revision, and visibility gates | Explicitly records that no source owner or signed attestation is present |
| `docs/forecast-quality/q2d-label-authority-evidence-matrix.md` | Enumerates required source fields and acceptable evidence | Matrix entries remain unverified without an attested source |
| `docs/forecast-quality/q2d-backtest-readiness-gate.md` | Keeps backtest fail-closed while attestation is absent | A readiness contract is not proof of the underlying source |
| `docs/forecast-quality/q2c-physical-target-equivalence-contract.md` | Freezes FARM_PICK / observed-weight / KG target semantics | Does not identify a business owner or prove physical equivalence |
| `docs/forecast-quality/q2c-physical-target-evidence-audit.md` | Separates implemented import semantics from real business evidence | No live business attestation or verified historical rows are supplied |
| `docs/forecast-quality/q2a-actual-harvest-source-contract.md` | Defines append-only source, identity, revision, and source-time requirements | Software validation rules do not establish who owns the source |
| `docs/forecast-quality/q2a-actual-harvest-spreadsheet-contract.md` | Defines canonical input and source-time authority statuses | A spreadsheet contract is not a signed dataset release or visibility manifest |
| `docs/forecast-quality/q2b-source-authority-and-leakage-audit.md` | Identifies receipt data as a forbidden proxy and real FARM_PICK rows as unverified | Does not provide a formal source owner attestation |
| Issue #102 Q2D governance records | Preserve `BLOCKED_BY_MISSING_SOURCE_OWNER` and `ACTUAL_LABEL_STATUS=UNVERIFIED` | Governance records acknowledge the gate; they do not satisfy it |

No source-owned SOP, data dictionary, release manifest, governance registry
record, or versioned business attestation was available in the inspected
repository evidence.

## 3. Evidence matrix

| Gate | Required proof | Current evidence | Result |
|---|---|---|---|
| A: source authority | Formal role or governed system, stable source identity, version, effective attestation | No accountable owner, governed authority, source version, or attestation record | `BLOCKED_BY_MISSING_SOURCE_OWNER` |
| B: measurement boundary | FARM_PICK event, weighing point/timing, population, sorting, postharvest, tare, calibration, precision | Target semantics are frozen by contract but process evidence is absent | `UNVERIFIED` |
| C: date and grain | Farm-local date authority, timezone/day boundary, identity policy, missing-day and correction rules | Software policy exists; source authority and released historical evidence are absent | `UNVERIFIED` |
| D: revision and visibility | Revision authority, publication boundary, immutable snapshot or visibility manifest | Lineage implementation exists; business publication and as-of visibility evidence is absent | `UNVERIFIED` |
| E: target equivalence | Evidence that actual quantity and forecast candidate measure the same physical boundary | Not evaluated because Gates A-D are not attested | `NOT_EVALUATED` |

## 4. Explicit exclusions

The following are not accepted as source authority or physical evidence:

- developer or implementer statements;
- field names, model names, table names, test fixtures, or filenames;
- unsigned narrative descriptions;
- a current or latest mutable row;
- inferred owners or database users without governance authority;
- model output or forecast target fields;
- factory receipt, arrival, packhouse receipt, or other post-pick proxy;
- insertion order, upload time, file metadata, or server timestamps as historical visibility.

In particular, `FactReceiptDaily.weight_kg` is a receipt proxy and cannot prove
`FARM_PICK` observed weight.

## 5. Data handling

```text
RAW_BUSINESS_DATA_INSPECTED=false
RAW_BUSINESS_DATA_EXPORTED=false
PERSONAL_DATA_COLLECTED=false
CREDENTIALS_COLLECTED=false
PRIVATE_URLS_RECORDED=false
```

This audit stores only contract references, evidence status, and missing-proof
descriptions. It does not store raw rows or personal identity details.

## 6. Conclusion

The repository provides deterministic contracts for what a valid attestation
must prove, but no formal source owner or governed source-system authority has
provided a versioned attestation. The physical measurement, date/grain, and
historical visibility gates therefore remain unverified and the final status
is fail-closed.

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
Q2E_CURRENT_STATUS=BLOCKED_BY_MISSING_SOURCE_OWNER
BUSINESS_ATTESTATION_READY=false
```
