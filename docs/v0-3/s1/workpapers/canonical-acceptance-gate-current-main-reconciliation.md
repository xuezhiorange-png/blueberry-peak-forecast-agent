# V0.3-S1 Canonical Acceptance Gate Current-Main Reconciliation

## 1. Scope and authority

```text
WORKPAPER_ID=V0_3_S1_CANONICAL_ACCEPTANCE_GATE_CURRENT_MAIN_RECONCILIATION
TASK_CLASS=DOCS_ONLY_GOVERNANCE_RECONCILIATION
AUDITED_REPOSITORY_SHA=e0ffc184aaca32fda196fdd2f39a7dfa00376a56
CANONICAL_GATE_COUNT=17
CANONICAL_ACCEPTANCE_STATUS=BLOCKED
CANONICAL_ACCEPTANCE_STATUS_MUTATION_ALLOWED=true
CURRENT_TASK_CANONICAL_GATE_STATUS_MUTATION_COUNT=0
CURRENT_TASK_CANONICAL_GATE_BLOCK_REASON_MUTATION_COUNT=0
S1_ACCEPTANCE_ISSUANCE_ALLOWED=false
SOURCE_002_READ=false
REAL_BUSINESS_DATA_READ=false
TEST_DATA_ACCESSED=false
EXTERNAL_HOLDOUT_DATA_ACCESSED=false
```

This workpaper reconciles current-main evidence against the existing
authoritative S1 gate registry. PR #219 issued and independently reviewed the
minimum-coverage policy; PR #221 closed the standalone minimum-coverage gate;
PR #222 issued and independently reviewed the separate data-quality policy, and
PR #238 issued and independently accepted the final Source Owner Attestation;
PR #241 issued and independently accepted the final Source Cohort Manifest,
and PR #243 issued and independently accepted the Q2C target decision, which
this closeout records as the fifth passing gate. It does not accept S1,
authorize S2, or read Source 002 raw rows. The current
main artifact wins over historical PR descriptions when they differ; PR
history is used only as provenance for already merged implementation work.

The authoritative completion rule remains:

```text
COMPLETION_RULE=ALL_17_REQUIRED_GATE_ROWS_STATUS_PASS
CURRENT_CANONICAL_GATE_PASS_COUNT=5
CURRENT_CANONICAL_GATE_BLOCKED_COUNT=12
FACT_LAYER_COMPLETE=true
FORMAL_ATTESTATIONS_ISSUED=true
INDEPENDENT_GATE_LOCAL_REVIEW_PENDING=true
CANONICAL_GATE_ACCEPTANCE_PENDING=true
PHYSICAL_MEANING_ATTESTATION_STATUS=ISSUED_PENDING_INDEPENDENT_REVIEW
PHYSICAL_MEANING_ATTESTATION_VERSION=source-002-physical-meaning-attestation-v1
PHYSICAL_MEANING_ATTESTATION_HASH=1cacd18aa17797ba229b0198240ef41e753cb9db2763fd7681828e7a77ff3944
UNIT_TIME_BASIS_ATTESTATION_STATUS=ISSUED_PENDING_INDEPENDENT_REVIEW
UNIT_TIME_BASIS_ATTESTATION_VERSION=source-002-unit-time-basis-attestation-v1
UNIT_TIME_BASIS_ATTESTATION_HASH=d6a58c61a8e0f789e928ef26e864a7e995c50a891b3452c7dc6a6fc6645f17ee
PHYSICAL_MEANING_ACCEPTED=false
UNIT_TIME_BASIS_ACCEPTED=false
ALL_CANONICAL_RUNTIME_STATUS_BLOCKED=false
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

None of these classes alone means `PASS` or `ACCEPTED`. The companion artifact
records the four separately closed rows explicitly; all remaining
blocked rows retain `can_be_closed_by_current_task=false`.

### Dependency semantics

The reconciliation separates three graphs that were previously conflated:

1. **Gate hard-prerequisite graph** — `hard_prerequisite_gate_ids` are
   directional strict prerequisites: the referenced gate or accepted artifact
   must close before the current gate can close. This graph must be acyclic.
2. **Gate co-resolution graph** — `co_resolution_gate_ids` identify gates that
   may be formalized in the same decision package. They are not prerequisites;
   mutual relationships are therefore allowed and do not create a hard-cycle.
3. **Packaged execution-task graph** — each package's `dependencies` points
   only to earlier `S1-REMAINING-*` task packages. It describes execution
   order, not gate closure semantics.

Accordingly:

```text
GATE_HARD_PREREQUISITE_GRAPH != CO_RESOLUTION_GRAPH
GATE_HARD_PREREQUISITE_GRAPH != PACKAGED_EXECUTION_TASK_GRAPH
CO_RESOLUTION_GRAPH != PACKAGED_EXECUTION_TASK_GRAPH
HARD_PREREQUISITE_IS_DIRECTIONAL=true
HARD_PREREQUISITE_GRAPH_MUST_BE_ACYCLIC=true
CO_RESOLUTION_IS_NOT_PREREQUISITE=true
CO_RESOLUTION_RELATIONSHIP_MAY_BE_MUTUAL=true
```

The machine-readable validation records zero hard-prerequisite cycles,
self-dependencies, or unknown gate references. The six packaged task
dependencies are validated separately as a directional acyclic task graph.

## 2. Current canonical runtime state

The current acceptance record at
`docs/v0-3/s1/evidence/s1-acceptance-record.json` contains exactly the 17
required gate IDs, each once. `S1-MINIMUM-COVERAGE`,
`S1-DATA-QUALITY-THRESHOLDS`, `S1-SOURCE-AUTHORITY`, `S1-SOURCE-COHORT`, and
`S1-Q2C-TARGET` are `PASS`; the other twelve rows remain `BLOCKED`. Historical block reasons are preserved in the
reconciliation artifact, but are not copied as if they were a current factual
audit without checking later evidence.

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
  current-main PIT records. Their merged implementation status is separate
  from canonical gate acceptance; PR #222's reviewed owner policy is bound by
  this closeout for the data-quality gate only.
- PR #243's issued business-source attestation and final Q2C decision are
  independently reviewed and merged; Q2C is accepted only at its own
  canonical gate and does not accept Physical Meaning, Unit/Time Basis, or
  any downstream gate.

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

| Gate | Runtime | Reconciliation class | Existing evidence | True remaining blocker | Hard prerequisite | Co-resolution | Recommended next action |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `S1-Q2C-TARGET` | `PASS` | `FORMALIZATION_OR_REVIEW_READY` | Issued business-source attestation and Q2C decision bind `OBSERVED_FARM_PICK_QUANTITY`, `PROVEN_EXACT`, six exact dimensions, and no transformation; PR #243 review and CI passed before merge. | None for Q2C; Physical Meaning and Unit/Time Basis remain separate gate-local closeouts. | None | None | Preserve Physical Meaning, Unit/Time Basis, and downstream gate blockers. |
| `S1-SOURCE-AUTHORITY` | `PASS` | `FORMALIZATION_OR_REVIEW_READY` | Final Source Owner Attestation, owner role, effective time, completeness binding, and attestation hash are present; PR #238 exact-head review `4946622009` and CI `31955752008` passed before merge `d3828041f15d9bba0b201429250a2041bcf63c2f`. | None for Source Authority; Source Cohort is separately accepted by PR #241, while Q2C and other gates remain separate. | None | None | Preserve Q2C and downstream gate blockers. |
| `S1-SOURCE-COHORT` | `PASS` | `FORMALIZATION_OR_REVIEW_READY` | Final manifest `source-002-final-source-cohort-manifest-v1` binds cohort `source-002-s1-cohort-v1`, hash `27ddb9a77d9ce7d4b0579d0648c23b5ade7d6a090626b695e5b41827e714fcca`, 84 farms, 192 subfarms, 20 varieties, business dates `2025-08-05..2026-04-16`, 233171 rows, and 28668416 bytes; PR #241 review `4948013727` and CI `31986614521` passed before merge `5caa63a20ee45b7e725b3c2c696a41cd3dd4a06b`. | None for Source Cohort; S1 freezes identity only and S2 owns the final materialized rowset. | None | None | Preserve canonical-grain, inclusion/exclusion, visibility, custody, split, Q2C, and other gate blockers. |
| `S1-PHYSICAL-MEANING` | `BLOCKED` | `FORMALIZATION_OR_REVIEW_READY` | Issued Physical Meaning Attestation binds the scan-weigh event, marketable net weight, KG, sorting, rejection, and recorded-label semantics. | Independent gate-local review and hash verification remain pending; runtime block reason is preserved. | `S1-SOURCE-AUTHORITY` | `S1-Q2C-TARGET` | Independently review the issued Physical Meaning Attestation, then perform gate-local closeout. |
| `S1-UNIT-AND-TIME-BASIS` | `BLOCKED` | `FORMALIZATION_OR_REVIEW_READY` | Issued Unit/Time Basis Attestation binds KG, Asia/Shanghai, local-day rule, business-date rule, and grain context. | Independent gate-local review and hash verification remain pending; runtime block reason is preserved. | `S1-SOURCE-AUTHORITY` | `S1-Q2C-TARGET`; `S1-INCLUSION-EXCLUSION` | Independently review the issued Unit/Time Basis Attestation, then perform gate-local closeout. |
| `S1-CANONICAL-GRAIN` | `BLOCKED` | `UPSTREAM_DEPENDENCY_BLOCKED` | Canonical grain and aggregate scope support are present; the separate canonical-grain/mapping gate remains unaccepted. | Accepted mapping applicability and canonical-grain review are required before grain can be frozen. | `S1-SOURCE-AUTHORITY` | `S1-SOURCE-COHORT`; `S1-INCLUSION-EXCLUSION` | Formalize grain after source authority and mapping review. |
| `S1-VISIBILITY` | `BLOCKED` | `NARROW_CORRECTION_REQUIRED` | Current PIT evidence is 4/17/0/1; PR #189/#190/#192/#194 controls are represented. | Four current gaps remain: planning provenance, Analytics taxonomy, Analytics source cutoff, and Task9 mixed authority. | `S1-SOURCE-AUTHORITY`; `S1-Q2C-TARGET`; `S1-SOURCE-COHORT`; `S1-CANONICAL-GRAIN`; `S1-INCLUSION-EXCLUSION` | None | Close the four PIT source-class and mixed-authority gaps. |
| `S1-REVISION-WINNER` | `BLOCKED` | `UPSTREAM_DEPENDENCY_BLOCKED` | Q2A/I7 rules and IDFL mode semantics are defined; IDFL label-side winner is not required. | Source-specific disposition and applicability are not frozen or independently reviewed. | `S1-SOURCE-AUTHORITY`; `S1-MISSING-CORRECTION-CANCELLATION` | `S1-SOURCE-COHORT`; `S1-INCLUSION-EXCLUSION` | Reconcile the source-specific winner disposition after source/cohort freeze. |
| `S1-INCLUSION-EXCLUSION` | `BLOCKED` | `EXTERNAL_AUTHORITY_OR_DECISION_REQUIRED` | Inclusion manifest records retained unmapped rows, no auto-July assignment, and unknown-not-zero; Source Cohort identity is accepted separately. | Unmapped-date and scope applicability decisions remain pending. | `S1-SOURCE-AUTHORITY` | `S1-SOURCE-COHORT`; `S1-CANONICAL-GRAIN` | Resolve unmapped-date and source-scope inclusion/exclusion authority. |
| `S1-MISSING-CORRECTION-CANCELLATION` | `BLOCKED` | `EXTERNAL_AUTHORITY_OR_DECISION_REQUIRED` | Missingness and IDFL mode semantics are defined; custody propagation is separate. | Source completeness, missing-day, correction, void, and final-confirmation authority remain incomplete. | `S1-SOURCE-AUTHORITY` | None | Issue source completeness and lifecycle policy authority. |
| `S1-SPLIT-POLICY` | `BLOCKED` | `UPSTREAM_DEPENDENCY_BLOCKED` | Time-ordering, no leakage, TEST seal, and custody rules are defined. | The Source Cohort identity is accepted, but no accepted final clean rowset or final split artifact exists. | `S1-SOURCE-COHORT`; `S1-INCLUSION-EXCLUSION`; `S1-VISIBILITY`; `S1-METRIC-CONTRACT`; `S1-DATA-CUSTODY` | None | Prepare split/custody artifact after remaining upstream acceptance. |
| `S1-METRIC-CONTRACT` | `BLOCKED` | `UPSTREAM_DEPENDENCY_BLOCKED` | Metric identities, S3 binding rules, and the independently reviewed minimum-coverage and data-quality policies are defined. | Source/target/visibility/rowset prerequisites and an accepted metric binding still prevent metric acceptance. | `S1-Q2C-TARGET`; `S1-SOURCE-AUTHORITY`; `S1-SOURCE-COHORT`; `S1-VISIBILITY`; `S1-MINIMUM-COVERAGE`; `S1-DATA-QUALITY-THRESHOLDS` | None | Freeze metric contract after the remaining upstream authority decisions. |
| `S1-MINIMUM-COVERAGE` | `PASS` | `FORMALIZATION_OR_REVIEW_READY` | Versioned owner policy, SHA-256 binding, independent review `4937929668`, and exact-head CI `31806575112` are present. | None for this standalone gate; downstream metric/cohort prerequisites remain separate. | None | None | Revalidate Remaining-05 after the minimum-coverage gate closeout. |
| `S1-DATA-QUALITY-THRESHOLDS` | `PASS` | `FORMALIZATION_OR_REVIEW_READY` | Versioned owner policy, SHA-256 binding, independent review `4943327077`, and exact-head CI `31872490353` are present. | None for this standalone policy gate; Source 002 execution and downstream gates remain separate. | None | None | Revalidate Remaining-05 after the data-quality gate closeout. |
| `S1-DATA-CUSTODY` | `BLOCKED` | `FORMALIZATION_OR_REVIEW_READY` | Versioned custody record, policy identities, hashes, access, retention, withdrawal, and void propagation are issued for review. | Independent custody review/acceptance is absent. | `S1-SOURCE-AUTHORITY` | `S1-SOURCE-COHORT` | Submit the issued custody record for independent review. |
| `S1-HOLDOUT-FEASIBILITY` | `BLOCKED` | `UPSTREAM_DEPENDENCY_BLOCKED` | Feasibility rule and no-data boundary are clear; no TEST/holdout was accessed. | Source Cohort identity is accepted, but no accepted final clean rowset, distinct-cohort coverage summary, custody, split, or reviewed feasibility decision exists. | `S1-SOURCE-COHORT`; `S1-CANONICAL-GRAIN`; `S1-INCLUSION-EXCLUSION`; `S1-VISIBILITY`; `S1-MINIMUM-COVERAGE`; `S1-DATA-CUSTODY`; `S1-SPLIT-POLICY` | None | Prepare and review feasibility after prerequisites close. |
| `S1-INDEPENDENT-REVIEW` | `BLOCKED` | `UPSTREAM_DEPENDENCY_BLOCKED` | Registry has 17 required rows; review status is not started. | All required gate artifacts must close before independent S1 review. | All other 16 gates | None | Run final independent S1 acceptance review. |

## 5. Gate-by-gate findings

The machine-readable artifact is the field-level record for every row. The
following cross-cutting findings explain the important status corrections:

1. `S1-PHYSICAL-MEANING` and `S1-UNIT-AND-TIME-BASIS` are not treated as
   missing-fact rows merely because their preserved runtime block reasons are
   `MISSING_MEASUREMENT_BOUNDARY` and `UNIT_OR_TIME_AUTHORITY_MISSING`.
   Current main contains the reconciled fact layer and both formal attestations
   are issued; independent gate-local review is still required.
2. `S1-DATA-QUALITY-THRESHOLDS` is closed only at the policy-governance layer:
   the accepted versioned policy is not a data execution result. `S1-DATA-CUSTODY`
   has a versioned custody record issued for review. It is
   not accepted, but the current remaining problem is review/acceptance rather
   than a missing storage, role, retention, withdrawal, or void fact.
3. Source identity and Source 002 scope hashes remain evidence bindings, not
   substitutes for unrelated gates. The merged final Source Owner Attestation,
   final Source Cohort Manifest, and Q2C closeout now make
   `SOURCE_AUTHORITY_ACCEPTED=true`, `SOURCE_COHORT_ACCEPTED=true`, and
   `Q2C_ACCEPTED=true`; Physical Meaning and Unit/Time Basis remain separate
   and unaccepted.
4. The IDFL_V1 design acceptance is a cross-contract mode-semantic decision;
   it does not accept Source 002, remove source completeness requirements, or
   close the canonical revision/visibility gates.
5. PIT `4 PASS / 17 PARTIAL / 0 BLOCKED / 1 NOT_USED` is retained as one
   evidence domain. It does not become four total S1 remaining tasks.
6. No threshold is inferred from `MIN_COMPARABLE_ROWS_FOR_REPORTING=10`,
   Source 002 row counts, or scope counts.

## 6. Cross-gate dependency graph

The following graph contains only strict `hard_prerequisite_gate_ids`; no
co-resolution edge is drawn as a prerequisite arrow:

```text
SOURCE-AUTHORITY
  ├── Q2C-TARGET
  ├── PHYSICAL-MEANING
  ├── UNIT-AND-TIME-BASIS
  ├── SOURCE-COHORT
  ├── INCLUSION-EXCLUSION
  ├── CANONICAL-GRAIN
  ├── MISSING-CORRECTION-CANCELLATION
  └── DATA-CUSTODY

MISSING-CORRECTION-CANCELLATION
  └── REVISION-WINNER

Q2C-TARGET + SOURCE-COHORT + CANONICAL-GRAIN + INCLUSION-EXCLUSION
  └── VISIBILITY

SOURCE-COHORT
  └── MINIMUM-COVERAGE

SOURCE-COHORT + INCLUSION-EXCLUSION
  └── DATA-QUALITY-THRESHOLDS

Q2C-TARGET + SOURCE-AUTHORITY + SOURCE-COHORT + VISIBILITY
  + MINIMUM-COVERAGE + DATA-QUALITY-THRESHOLDS
  └── METRIC-CONTRACT

SOURCE-COHORT + INCLUSION-EXCLUSION + VISIBILITY + METRIC-CONTRACT
  + DATA-CUSTODY
  └── SPLIT-POLICY

SOURCE-COHORT + CANONICAL-GRAIN + INCLUSION-EXCLUSION + VISIBILITY
  + MINIMUM-COVERAGE + DATA-CUSTODY + SPLIT-POLICY
  └── HOLDOUT-FEASIBILITY

ALL_REQUIRED_GATES
  └── INDEPENDENT-REVIEW
        └── S1_ACCEPTED (separate decision)
              └── S2_MAY_BE_AUTHORIZED (not automatic)
```

The hard-prerequisite validation is:

```text
HARD_PREREQUISITE_NODE_COUNT=17
HARD_PREREQUISITE_CYCLE_FOUND=false
HARD_PREREQUISITE_CYCLE_COUNT=0
SELF_DEPENDENCY_COUNT=0
UNKNOWN_GATE_REFERENCE_COUNT=0
TOPOLOGICAL_ORDER_VALID=true
TOPOLOGICAL_ORDER_GATE_COUNT=17
```

### Co-resolution groups

These relationships are package-level collaboration, not strict dependency
arrows:

- `S1-Q2C-TARGET` + `S1-PHYSICAL-MEANING` + `S1-UNIT-AND-TIME-BASIS`
- `S1-SOURCE-COHORT` + `S1-CANONICAL-GRAIN` +
  `S1-INCLUSION-EXCLUSION`
- `S1-REVISION-WINNER` + `S1-SOURCE-COHORT` +
  `S1-INCLUSION-EXCLUSION`
- `S1-DATA-CUSTODY` + `S1-SOURCE-COHORT`

Mutual membership in these groups does not create a hard-prerequisite cycle.

## 7. Evidence-ready formalization queue

These are not accepted gates; they are the shortest queue for artifacts whose
current facts are substantially present:

- Independently review the issued physical-meaning attestation, then perform
  the gate-local closeout without changing its BLOCKED runtime status here.
- Independently review the issued unit/time attestation, then perform the
  gate-local closeout without changing its BLOCKED runtime status here.
- Submit the issued custody record and its hashes for independent review.
- Preserve the accepted Q2C target binding while formalizing the separate
  physical-meaning and unit/time gate artifacts.

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

- unmapped-date and source-scope inclusion/exclusion authority;
- source completeness, missing-day, correction, void, and lifecycle authority;

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

1. **Source authority and scope decision package** (`S1-REMAINING-01`,
   dependencies: none) — obtain the owner
   attestation and resolve applicability, completeness, scope, date, and
   inclusion authority.
2. **Physical/unit/time formalization** (`S1-REMAINING-02`, dependency:
   `S1-REMAINING-01`) — submit the issued separate physical-meaning and
   unit/time artifacts for independent gate-local review; the Q2C target is
   already accepted.
3. **Source cohort, canonical grain, inclusion, and revision artifacts**
   (`S1-REMAINING-03`, dependencies: `S1-REMAINING-01`,
   `S1-REMAINING-02`) — freeze the accepted source universe and source-specific lifecycle
   disposition.
4. **Narrow PIT visibility correction** (`S1-REMAINING-04`, dependencies:
   `S1-REMAINING-01`, `S1-REMAINING-02`, `S1-REMAINING-03`) — close the four current source-class
   and mixed-authority gaps, then revalidate visibility evidence.
5. **Threshold, metric, split, and holdout package** (`S1-REMAINING-05`,
   dependencies: `S1-REMAINING-03`, `S1-REMAINING-04`; required gate artifact:
   `S1-DATA-CUSTODY`) — decide thresholds,
   freeze metrics, prepare the time-ordered split, and review holdout
   feasibility without accessing TEST or external holdout in this task.
6. **Final independent S1 acceptance review** (`S1-REMAINING-06`, dependencies:
   `S1-REMAINING-01` through `S1-REMAINING-05`) — only after all required rows
   have complete artifacts.

The six packaged task graph has six nodes, zero cycles, and a valid
topological order matching the list above. The `S1-DATA-CUSTODY` reference in
package 5 is a required gate artifact, not a package-task dependency; it is
not mixed into the task graph. This order is dependency-based. It does not
authorize the first item or imply the next item automatically.

## 12. S1 acceptance boundary

This workpaper updates the current evidence identity for the two target rows
to the issued attestations while preserving their canonical runtime status and
block reasons. It does not accept Physical Meaning, Unit/Time Basis, custody,
or final S1 acceptance and does not claim S1 completion. The authoritative
record remains:

```text
CURRENT_CANONICAL_GATE_PASS_COUNT=5
CURRENT_CANONICAL_GATE_BLOCKED_COUNT=12
PHYSICAL_MEANING_ACCEPTED=false
UNIT_TIME_BASIS_ACCEPTED=false
V0_3_S1_COMPLETE=false
V0_3_S1_ACCEPTED=false
```

## 13. Historical Source Authority closeout

```text
POST_PR238_CURRENT_MAIN_REVALIDATION=PASS
PR238_MERGED=true
PR238_HEAD_SHA=9b181f4e160981dca7a28fa584855e70a9555f34
PR238_MERGE_COMMIT_SHA=d3828041f15d9bba0b201429250a2041bcf63c2f
SOURCE_AUTHORITY_INDEPENDENT_REVIEW_ID=4946622009
SOURCE_AUTHORITY_INDEPENDENT_REVIEW_RESULT=PASS
SOURCE_AUTHORITY_EXACT_HEAD_CI_RUN_ID=31955752008
SOURCE_AUTHORITY_EXACT_HEAD_CI_CONCLUSION=success
SOURCE_AUTHORITY_ACCEPTED=true
SOURCE_COHORT_ACCEPTED=false
Q2C_ACCEPTED=false
CURRENT_CANONICAL_GATE_PASS_COUNT=3
CURRENT_CANONICAL_GATE_BLOCKED_COUNT=14
SOURCE_AUTHORITY_CLOSEOUT_SCOPE_ONLY=true
NO_DOWNSTREAM_GATE_ACCEPTANCE_PERFORMED=true
```

This is the historical PR #238 closeout snapshot retained as provenance. It
does not describe the current post-PR241 Source Cohort state.

## 14. Historical Source Cohort canonical closeout

```text
POST_PR241_CURRENT_MAIN_REVALIDATION=PASS
PR241_MERGED=true
PR241_HEAD_SHA=b856d3823e51bb6e4f8b780363203a1c477677ca
PR241_MERGE_COMMIT_SHA=5caa63a20ee45b7e725b3c2c696a41cd3dd4a06b
SOURCE_COHORT_INDEPENDENT_REVIEW_ID=4948013727
SOURCE_COHORT_INDEPENDENT_REVIEW_GRAPHQL_ID=PRR_kwDOS_gTTs8AAAABJuyynw
SOURCE_COHORT_REVIEWED_AT=2026-08-17T02:25:52Z
SOURCE_COHORT_EXACT_HEAD_CI_RUN_ID=31986614521
SOURCE_COHORT_EXACT_HEAD_CI_CONCLUSION=success
SOURCE_COHORT_MANIFEST_VERSION=source-002-final-source-cohort-manifest-v1
SOURCE_COHORT_ID=source-002-s1-cohort-v1
SOURCE_COHORT_MANIFEST_HASH=27ddb9a77d9ce7d4b0579d0648c23b5ade7d6a090626b695e5b41827e714fcca
SOURCE_AUTHORITY_ACCEPTED=true
SOURCE_COHORT_ACCEPTED=true
Q2C_ACCEPTED=false
CURRENT_CANONICAL_GATE_PASS_COUNT=4
CURRENT_CANONICAL_GATE_BLOCKED_COUNT=13
SOURCE_COHORT_GATE_ONLY_STATUS_MUTATION=PASS
OTHER_GATE_STATUS_MUTATION_COUNT=0
S1_FREEZES_SOURCE_COHORT_IDENTITY=true
S1_FREEZES_FINAL_CLEAN_ROWSET=false
S2_OWNS_FINAL_MATERIALIZED_ROWSET=true
V0_3_S1_ACCEPTED=false
V0_3_S2_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```

This is the historical post-PR241 snapshot. The Source Cohort closeout was
gate-local and did not accept Q2C, canonical grain, inclusion/exclusion,
visibility, revision, custody, split, holdout, or final S1 review. The later
PR #243 closeout is the current Q2C state.

## 15. S2 authorization boundary

The development plan states `S1_ACCEPTED -> S2_MAY_BE_AUTHORIZED`. This is a
prerequisite relation, not automatic authorization. This workpaper creates no
S2 task and leaves:

```text
V0_3_S2_AUTHORIZED=false
V0_3_S2_STARTED=false
NO_STEP_IMPLIES_THE_NEXT=true
```

## 16. Reconciliation summary

```text
RECONCILED_GATE_COUNT=17
UNIQUE_GATE_ID_COUNT=17
MISSING_GATE_COUNT=0
DUPLICATE_GATE_COUNT=0
FORMALIZATION_OR_REVIEW_READY_COUNT=8
NARROW_CORRECTION_REQUIRED_COUNT=1
EXTERNAL_AUTHORITY_OR_DECISION_REQUIRED_COUNT=2
UPSTREAM_DEPENDENCY_BLOCKED_COUNT=6
CLASSIFICATION_COUNT_SUM=17
HARD_PREREQUISITE_CYCLE_FOUND=false
HARD_PREREQUISITE_CYCLE_COUNT=0
SELF_DEPENDENCY_COUNT=0
UNKNOWN_GATE_REFERENCE_COUNT=0
TOPOLOGICAL_ORDER_VALID=true
TOPOLOGICAL_ORDER_GATE_COUNT=17
TASK_PACKAGE_COUNT=6
TASK_PACKAGE_DEPENDENCY_CYCLE_FOUND=false
TASK_PACKAGE_TOPOLOGICAL_ORDER_VALID=true
PIT_MINIMUM_IMPLEMENTATION_GAP_COUNT=4
PIT_GAPS_TREATED_AS_S1_TOTAL_REMAINING_TASKS=false
AUTHORITATIVE_ACCEPTANCE_RECORD_CHANGED=true
CANONICAL_GATE_STATUS_CHANGED=true
```
