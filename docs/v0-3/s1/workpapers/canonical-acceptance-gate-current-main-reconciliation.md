# V0.3-S1 Canonical Acceptance Gate Current-Main Reconciliation

## 1. Scope and authority

```text
WORKPAPER_ID=V0_3_S1_CANONICAL_ACCEPTANCE_GATE_CURRENT_MAIN_RECONCILIATION
TASK_CLASS=DOCS_ONLY_GOVERNANCE_RECONCILIATION
AUDITED_REPOSITORY_SHA=5b3f4ee1ac7e25698b4ef54ab9a2915323e5317d
CANONICAL_GATE_COUNT=17
CANONICAL_ACCEPTANCE_STATUS=BLOCKED
CANONICAL_ACCEPTANCE_STATUS_MUTATION_ALLOWED=false
S1_ACCEPTANCE_ISSUANCE_ALLOWED=false
SOURCE_002_READ=false
REAL_BUSINESS_DATA_READ=false
TEST_DATA_ACCESSED=false
EXTERNAL_HOLDOUT_DATA_ACCESSED=false
```

This workpaper reconciles current-main evidence against the existing
authoritative S1 gate registry. It does not change the registry, issue a gate
decision, accept S1, authorize S2, or read Source 002 raw rows. The current
main artifact wins over historical PR descriptions when they differ; PR
history is used only as provenance for already merged implementation work.

The authoritative completion rule remains:

```text
COMPLETION_RULE=ALL_17_REQUIRED_GATE_ROWS_STATUS_PASS
CURRENT_CANONICAL_GATE_PASS_COUNT=0
CURRENT_CANONICAL_GATE_BLOCKED_COUNT=17
V0_3_S1_COMPLETE=false
V0_3_S1_ACCEPTED=false
V0_3_S2_AUTHORIZED=false
V0_3_S2_STARTED=false
```

The four reconciliation classes are independent of runtime status:

| Class | Meaning in this workpaper |
| --- | --- |
| `FORMALIZATION_OR_REVIEW_READY` | Evidence is substantially present; the remaining step is a formal artifact/review boundary. |
| `NARROW_CORRECTION_REQUIRED` | A bounded repository implementation/provenance/reconciliation gap remains; no new business fact is being invented. |
| `EXTERNAL_AUTHORITY_OR_DECISION_REQUIRED` | A source owner, business owner, governance owner, or validation-policy authority must provide or approve a value/decision not derivable from current main. |
| `UPSTREAM_DEPENDENCY_BLOCKED` | The rule is known, but a prerequisite gate/artifact must close first. |

None of these classes means `PASS` or `ACCEPTED`. All rows in the machine-
readable companion artifact have `can_be_closed_by_current_task=false`.

## 2. Current canonical runtime state

The current acceptance record at
`docs/v0-3/s1/evidence/s1-acceptance-record.json` contains exactly the 17
required gate IDs, each once, with `status=BLOCKED`. Its historical block
reasons are preserved in the reconciliation artifact, but are not copied as if
they were a current factual audit without checking later evidence.

The current main contains meaningful evidence beyond the initial registry:

- Q2C physical facts are reconciled at the fact layer, including the recorded
  scan-weigh label boundary, marketable net weight, KG, local time, and grain.
- Source 002 identity, schema, snapshot, aggregate counts, scope-package
  hashes, inclusion/exclusion preparation, and custody evidence exist.
- The custody record is issued for independent review, while custody
  acceptance remains false.
- PIT evidence is `4 PASS / 17 PARTIAL / 0 BLOCKED / 1 NOT_USED` over 22 rows;
  its four implementation gaps are a single evidence domain, not four total
  S1 tasks.
- PR #189, #190, #192, and #194 implementation evidence is represented in
  current-main PIT records. Their merged status does not change any canonical
  S1 runtime row to PASS.

## 3. Current-main evidence sources reviewed

### Canonical S1 authority and contracts

- `docs/v0-3/development-plan.md`
- `docs/v0-3/s1/index.md`
- `docs/v0-3/s1/s1-acceptance-package.md`
- `docs/v0-3/s1/evidence/s1-acceptance-record.json`
- `docs/v0-3/s1/schemas/s1-acceptance-record.schema.json`
- `docs/v0-3/s1/target-decision-and-quantity-contract.md`
- `docs/v0-3/s1/source-authority-and-cohort-manifest.md`
- `docs/v0-3/s1/visibility-inclusion-revision-contract.md`
- `docs/v0-3/s1/split-holdout-and-custody-contract.md`
- `docs/v0-3/s1/metric-coverage-and-quality-contract.md`

### Current evidence registry and Package A evidence

- `docs/v0-3/s1/evidence/evidence-package-manifest.json`
- `docs/v0-3/s1/evidence/q2c-physical-alignment-evidence-status.md`
- `docs/v0-3/s1/evidence/source-authority-evidence-status.md`
- `docs/v0-3/s1/evidence/source-cohort-evidence-status.md`
- `docs/v0-3/s1/evidence/data-custody-evidence-status.md`
- `docs/v0-3/s1/evidence/threshold-decision-evidence-status.md`
- `docs/v0-3/s1/evidence/holdout-feasibility-evidence-status.md`
- `docs/v0-3/s1/evidence/forecast-input-point-in-time-leakage-audit.json`
- `docs/v0-3/s1/evidence/source-002-mapping-and-scope-identity-manifest.json`
- `docs/v0-3/s1/evidence/source-002-inclusion-exclusion-manifest.json`
- `docs/v0-3/s1/evidence/source-002-custody-record.json`
- `docs/v0-3/s1/evidence/source-002-governed-snapshot-evidence.md`
- `docs/v0-3/s1/evidence/source-002-completeness-and-custody-business-evidence.md`

### Workpapers and higher-precedence contracts

The reviewed workpaper set includes the Q2C, measurement/finalization,
season-calendar, source-schema, business-attestation, IDFL, immutable-label,
actual-label lifecycle, custody, and PIT workpapers under
`docs/v0-3/s1/workpapers/`. Higher-precedence contracts reviewed include:

- `docs/forecast-quality/q2c-physical-target-equivalence-contract.md`
- `docs/forecast-quality/q2a-i7-label-snapshot-and-revision-winner-contract.md`
- `docs/forecast-quality/q2a-actual-harvest-source-contract.md`
- `docs/forecast-quality/s3-quality-metrics-contract.md`
- `docs/v0-1/core-forecast-contract.md`

## 4. 17-gate reconciliation matrix

| Gate | Runtime | Reconciliation class | Existing evidence | True remaining blocker | Dependency | Recommended next action |
| --- | --- | --- | --- | --- | --- | --- |
| `S1-Q2C-TARGET` | `BLOCKED` | `EXTERNAL_AUTHORITY_OR_DECISION_REQUIRED` | Physical facts and recorded-label boundary are present; Q2C status is `NOT_ISSUED`. | Business-source attestation and closed Q2C outcome are absent. | Source authority, cohort, physical meaning, unit/time | Obtain and formalize the Q2C business-source attestation and target decision. |
| `S1-SOURCE-AUTHORITY` | `BLOCKED` | `EXTERNAL_AUTHORITY_OR_DECISION_REQUIRED` | Source identity, schema, snapshot, hashes, owner role, and Package A references are present. | Issued owner attestation, effective applicability, completeness, and attestation hash are absent. | None | Formalize and obtain source-owner authority. |
| `S1-SOURCE-COHORT` | `BLOCKED` | `EXTERNAL_AUTHORITY_OR_DECISION_REQUIRED` | Aggregate counts, object identity, scope hashes, and inclusion preparation exist. | Accepted schema-valid cohort manifest and cohort freeze are absent. | Source authority, inclusion/exclusion | Create and accept the versioned cohort manifest. |
| `S1-PHYSICAL-MEANING` | `BLOCKED` | `FORMALIZATION_OR_REVIEW_READY` | Scan-weigh event, marketable net weight, KG, sorting, rejection, and recorded-label semantics are reconciled. | Formal physical attestation and review/hash are absent. | Source authority, Q2C | Prepare the formal physical-meaning attestation. |
| `S1-UNIT-AND-TIME-BASIS` | `BLOCKED` | `FORMALIZATION_OR_REVIEW_READY` | KG, Asia/Shanghai, local-day rule, business-date rule, and canonical grain are recorded. | Formal unit/time authority binding and review are absent. | Source authority, inclusion/exclusion | Formalize the unit and farm-local time attestation. |
| `S1-CANONICAL-GRAIN` | `BLOCKED` | `UPSTREAM_DEPENDENCY_BLOCKED` | Canonical grain and aggregate scope support are present; mapping acceptance is false. | Accepted mapping/cohort scope is required before grain can be frozen. | Source authority, cohort, inclusion/exclusion | Formalize grain after source authority and mapping freeze. |
| `S1-VISIBILITY` | `BLOCKED` | `NARROW_CORRECTION_REQUIRED` | Current PIT evidence is 4/17/0/1; PR #189/#190/#192/#194 controls are represented. | Four current gaps remain: planning provenance, Analytics taxonomy, Analytics source cutoff, and Task9 mixed authority. | Source/cohort/Q2C authority | Close the four PIT source-class and mixed-authority gaps. |
| `S1-REVISION-WINNER` | `BLOCKED` | `UPSTREAM_DEPENDENCY_BLOCKED` | Q2A/I7 rules and IDFL mode semantics are defined; IDFL label-side winner is not required. | Source-specific disposition and applicability are not frozen or independently reviewed. | Source authority, cohort, inclusion, visibility | Reconcile the source-specific winner disposition after source/cohort freeze. |
| `S1-INCLUSION-EXCLUSION` | `BLOCKED` | `EXTERNAL_AUTHORITY_OR_DECISION_REQUIRED` | Inclusion manifest records retained unmapped rows, no auto-July assignment, and unknown-not-zero. | Unmapped-date and scope applicability decisions remain pending. | Source authority, cohort | Resolve unmapped-date and source-scope inclusion/exclusion authority. |
| `S1-MISSING-CORRECTION-CANCELLATION` | `BLOCKED` | `EXTERNAL_AUTHORITY_OR_DECISION_REQUIRED` | Missingness and IDFL mode semantics are defined; custody propagation is separate. | Source completeness, missing-day, correction, void, and final-confirmation authority remain incomplete. | Source authority, cohort, revision | Issue source completeness and lifecycle policy authority. |
| `S1-SPLIT-POLICY` | `BLOCKED` | `UPSTREAM_DEPENDENCY_BLOCKED` | Time-ordering, no leakage, TEST seal, and custody rules are defined. | No accepted cohort/rowset and no final split artifact exist. | Cohort, inclusion, visibility, metric, custody | Prepare split/custody artifact after upstream acceptance. |
| `S1-METRIC-CONTRACT` | `BLOCKED` | `UPSTREAM_DEPENDENCY_BLOCKED` | Metric identities and S3 binding rules are defined. | Source/target/visibility/threshold prerequisites prevent metric acceptance. | Q2C, source, visibility, coverage, quality | Freeze metric contract after upstream authority decisions. |
| `S1-MINIMUM-COVERAGE` | `BLOCKED` | `EXTERNAL_AUTHORITY_OR_DECISION_REQUIRED` | Status record explicitly says no approved S1 threshold; S3 floor 10 is not an S1 threshold. | Versioned coverage threshold decision is absent. | Cohort, metric | Obtain and accept an S1 coverage threshold decision. |
| `S1-DATA-QUALITY-THRESHOLDS` | `BLOCKED` | `EXTERNAL_AUTHORITY_OR_DECISION_REQUIRED` | No threshold is inferred; contract and status are fail-closed. | Versioned quality policy and threshold decision are absent. | Cohort, inclusion, metric | Obtain and accept the S1 quality-threshold policy. |
| `S1-DATA-CUSTODY` | `BLOCKED` | `FORMALIZATION_OR_REVIEW_READY` | Versioned custody record, policy identities, hashes, access, retention, withdrawal, and void propagation are issued for review. | Independent custody review/acceptance is absent. | Source authority, cohort | Submit the issued custody record for independent review. |
| `S1-HOLDOUT-FEASIBILITY` | `BLOCKED` | `UPSTREAM_DEPENDENCY_BLOCKED` | Feasibility rule and no-data boundary are clear; no TEST/holdout was accessed. | Accepted cohort, coverage, custody, split, and reviewed feasibility decision are absent. | Cohort, custody, split, coverage | Prepare and review feasibility after prerequisites close. |
| `S1-INDEPENDENT-REVIEW` | `BLOCKED` | `UPSTREAM_DEPENDENCY_BLOCKED` | Registry has 17 required rows; review status is not started. | All required gate artifacts must close before independent S1 review. | All other 16 gates | Run final independent S1 acceptance review. |

## 5. Gate-by-gate findings

The machine-readable artifact is the field-level record for every row. The
following cross-cutting findings explain the important status corrections:

1. `S1-PHYSICAL-MEANING` and `S1-UNIT-AND-TIME-BASIS` are not treated as
   missing-fact rows merely because the old acceptance record says
   `MISSING_MEASUREMENT_BOUNDARY` or `UNIT_OR_TIME_AUTHORITY_MISSING`. Current
   main contains the reconciled fact layer. Formal source attestation and
   review are still required.
2. `S1-DATA-CUSTODY` has a versioned custody record issued for review. It is
   not accepted, but the current remaining problem is review/acceptance rather
   than a missing storage, role, retention, withdrawal, or void fact.
3. Source identity and Source 002 scope hashes are evidence, not source
   authority or cohort acceptance. `SOURCE_AUTHORITY_ACCEPTED`,
   `SOURCE_COHORT_ACCEPTED`, and `Q2C_ACCEPTED` remain false.
4. The IDFL_V1 design acceptance is a cross-contract mode-semantic decision;
   it does not accept Source 002, remove source completeness requirements, or
   close the canonical revision/visibility gates.
5. PIT `4 PASS / 17 PARTIAL / 0 BLOCKED / 1 NOT_USED` is retained as one
   evidence domain. It does not become four total S1 remaining tasks.
6. No threshold is inferred from `MIN_COMPARABLE_ROWS_FOR_REPORTING=10`,
   Source 002 row counts, or scope counts.

## 6. Cross-gate dependency graph

```text
SOURCE-AUTHORITY
  ├── SOURCE-COHORT
  │     ├── CANONICAL-GRAIN
  │     ├── INCLUSION-EXCLUSION
  │     ├── REVISION-WINNER
  │     ├── SPLIT-POLICY
  │     └── HOLDOUT-FEASIBILITY
  ├── Q2C-TARGET
  │     ├── PHYSICAL-MEANING
  │     ├── UNIT-AND-TIME-BASIS
  │     └── METRIC-CONTRACT
  └── MISSING-CORRECTION-CANCELLATION

VISIBILITY
  ├── SPLIT-POLICY
  ├── METRIC-CONTRACT
  └── HOLDOUT-FEASIBILITY

MINIMUM-COVERAGE + DATA-QUALITY-THRESHOLDS
  └── METRIC-CONTRACT
        └── SPLIT-POLICY / HOLDOUT-FEASIBILITY

ALL_REQUIRED_GATES
  └── INDEPENDENT-REVIEW
        └── S1_ACCEPTED (separate decision)
              └── S2_MAY_BE_AUTHORIZED (not automatic)
```

## 7. Evidence-ready formalization queue

These are not accepted gates; they are the shortest queue for artifacts whose
current facts are substantially present:

- Prepare the physical-meaning attestation from the reconciled recorded-label
  fact layer.
- Prepare the unit/time attestation from KG, Asia/Shanghai, local-day, and
  canonical-grain facts.
- Submit the issued custody record and its hashes for independent review.
- After source authority is available, bind these artifacts into the formal
  Q2C and source/cohort packages.

## 8. Narrow correction queue

The current PIT audit identifies one canonical gate-level correction queue:
`S1-VISIBILITY`. It contains four implementation/authority gaps, not four
additional canonical S1 gates:

1. planning supplemental as-of effective plan identity/version/hash;
2. `ANALYTICS_FACTORY_RECEIPT` source-class taxonomy acceptance;
3. AnalyticsBuildRun source-cutoff binding for the realized cumulative
   composite; and
4. Task9 mixed exact-timestamp/local-date source-authority reconciliation.

These must be handled as a narrow, separately authorized correction package.
No production correction is executed by this reconciliation.

## 9. External authority / decision queue

The current main cannot derive or invent:

- source-owner attestation and applicability/effective-time authority;
- Q2C target equivalence outcome;
- unmapped-date and source-scope inclusion/exclusion authority;
- source completeness, missing-day, correction, void, and lifecycle authority;
- S1 minimum-coverage threshold; or
- S1 data-quality threshold policy.

The requested next decision package should ask only for these bounded
decisions/authorities. It must not repeat already evidenced Q2C physical facts,
Source 002 identity facts, or C1-C6 custody facts.

## 10. Dependency-blocked queue

The following cannot close until upstream artifacts are accepted:

- canonical grain;
- revision winner;
- split policy;
- metric contract;
- holdout feasibility; and
- final independent review.

The source cohort and source authority are the principal shared upstream
dependencies. `S1-INDEPENDENT-REVIEW` depends on all other required rows and
cannot be used to self-attest this workpaper.

## 11. Recommended execution order

1. **Source authority and scope decision package** — obtain the owner
   attestation and resolve applicability, completeness, scope, date, and
   inclusion authority.
2. **Q2C physical/unit/time formalization** — issue the formal target and
   measurement/time artifacts from the already reconciled facts.
3. **Source cohort, canonical grain, inclusion, and revision artifacts** —
   freeze the accepted source universe and source-specific lifecycle
   disposition.
4. **Narrow PIT visibility correction** — close the four current source-class
   and mixed-authority gaps, then revalidate visibility evidence.
5. **Threshold, metric, split, and holdout package** — decide thresholds,
   freeze metrics, prepare the time-ordered split, and review holdout
   feasibility without accessing TEST or external holdout in this task.
6. **Final independent S1 acceptance review** — only after all required rows
   have complete artifacts.

This order is dependency-based. It does not authorize the first item or imply
the next item automatically.

## 12. S1 acceptance boundary

This workpaper does not modify
`docs/v0-3/s1/evidence/s1-acceptance-record.json`. It does not set any runtime
gate to `PASS`, does not issue Q2C/source/cohort/custody acceptance, and does
not claim S1 completion. The authoritative record remains:

```text
CURRENT_CANONICAL_GATE_PASS_COUNT=0
CURRENT_CANONICAL_GATE_BLOCKED_COUNT=17
V0_3_S1_COMPLETE=false
V0_3_S1_ACCEPTED=false
```

## 13. S2 authorization boundary

The development plan states `S1_ACCEPTED -> S2_MAY_BE_AUTHORIZED`. This is a
prerequisite relation, not automatic authorization. This workpaper creates no
S2 task and leaves:

```text
V0_3_S2_AUTHORIZED=false
V0_3_S2_STARTED=false
NO_STEP_IMPLIES_THE_NEXT=true
```

## Reconciliation summary

```text
RECONCILED_GATE_COUNT=17
UNIQUE_GATE_ID_COUNT=17
MISSING_GATE_COUNT=0
DUPLICATE_GATE_COUNT=0
FORMALIZATION_OR_REVIEW_READY_COUNT=3
NARROW_CORRECTION_REQUIRED_COUNT=1
EXTERNAL_AUTHORITY_OR_DECISION_REQUIRED_COUNT=7
UPSTREAM_DEPENDENCY_BLOCKED_COUNT=6
CLASSIFICATION_COUNT_SUM=17
PIT_MINIMUM_IMPLEMENTATION_GAP_COUNT=4
PIT_GAPS_TREATED_AS_S1_TOTAL_REMAINING_TASKS=false
AUTHORITATIVE_ACCEPTANCE_RECORD_CHANGED=false
CANONICAL_GATE_STATUS_CHANGED=false
```
