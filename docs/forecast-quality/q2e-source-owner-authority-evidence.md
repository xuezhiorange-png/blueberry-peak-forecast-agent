# Q2E Source Owner Authority Evidence

```text
Q2E_ROUND=V0_2_S2_Q2E_BUSINESS_SOURCE_ATTESTATION
BASE_SHA=2e23441dade69fcdc74a64f2eccd220d40db5f27
SOURCE_OWNER=UNKNOWN
OWNER_INFERENCE_PERFORMED=false
ATTESTATION_STATUS=NOT_ATTESTED
```

## 1. Required authority record

An acceptable record must be issued by either a formal business role or a
governed source-system authority. It must identify a stable role or authority
code, not a person's name or contact details.

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

The required positive value is `attestation_status=ATTESTED`, with an
immutable or independently traceable source version and effective time.

## 2. Current evidence status

| Authority field | Required evidence | Current value | Status |
|---|---|---|---|
| `business_owner_role` | Formal accountable role or governed authority code | `UNKNOWN` | Missing |
| `source_system` | Stable governed system code | `UNVERIFIED` | Missing |
| `source_dataset` | Stable dataset or release code | `UNVERIFIED` | Missing |
| `source_version` | Immutable or traceable release version | `UNVERIFIED` | Missing |
| `source_snapshot_reference` | Immutable source snapshot or release manifest | `NONE` | Missing |
| `attestation_version` | Versioned signed/governed evidence record | `NONE` | Missing |
| `attestation_effective_at` | Effective time controlled by source authority | `NONE` | Missing |
| `attestation_status` | Formal approval state | `NOT_ATTESTED` | Not accepted |

No evidence in the repository identifies a source owner or governance system
with authority over the historical FARM_PICK dataset. `SOURCE_OWNER=UNKNOWN`
is an evidence result, not a claim that no such role exists in the business.

## 3. Authority responsibilities to attest

The future authority record must explicitly cover:

1. ownership of the source dataset and its release/version policy;
2. permission to define `FARM_PICK` and the observed-weight measurement event;
3. weighing location and timing relative to picking;
4. inclusion/exclusion of all picked fruit, sorting, rejected fruit, loss, tare,
   and postharvest handling;
5. farm-local date, timezone, day boundary, late-entry, and correction policy;
6. farm, subfarm/plot, variety, season, and canonical-grain identity policy;
7. logical-record and revision authority, including correction, void, and
   finalization rules;
8. publication boundary and immutable historical visibility manifest;
9. evidence version, effective interval, supersession policy, and review trail.

The authority must not use current/latest lookup, receipt date, insertion order,
upload metadata, or a mutable shared file as a substitute for historical
visibility.

## 4. Acceptance rule

Until all required fields are supplied by an acceptable authority and their
versioned evidence can be independently reviewed:

```text
SOURCE_OWNER_IDENTIFIED=NO
ATTESTATION_STATUS=NOT_ATTESTED
BUSINESS_ATTESTATION_READY=false
Q2E_CURRENT_STATUS=BLOCKED_BY_MISSING_SOURCE_OWNER
```

No positive attestation payload is created in this round. No personal names,
contact information, credentials, raw rows, or private URLs are required or
recorded.
