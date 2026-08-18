# S1 Metric Contract Owner-Decision Binding

## 1. Task and exact baseline

TASK_ID=S1_METRIC_CONTRACT_OWNER_DECISION_BINDING_RETRY_R1
TASK_CLASS=DOCS_ONLY_METRIC_CONTRACT_OWNER_DECISION_BINDING_AND_FORMALIZATION
SOURCE_ORIGINAL_TASK_ID=S1_METRIC_CONTRACT_OWNER_DECISION_BINDING_R1
RETRY_AUTHORIZATION_COMMENT_ID=5330733078
ORIGINAL_AUTHORIZATION_COMMENT_ID=5330446600
REPAIR_AUTHORIZATION_COMMENT_ID=5330592353
BASE_MAIN_SHA=4a5ae07ad9ed1f580c3e7627ded3acc719ba6bb2
BASE_MAIN_TREE_SHA=12f8f1e7d8b1d821d98cbea3354eafc1ecd2937c
NO_STEP_IMPLIES_THE_NEXT=true

This workpaper uses only the repaired fresh clone and binds the authenticated
owner decision in PR #256 comment `5330399072`. It does not modify the
authoritative metric contracts or canonical acceptance artifacts.

## 2. Owner decision identity

DECISION_ID=S1_METRIC_CONTRACT_FREEZE_AND_ACCEPTANCE
DECISION=ACCEPT
OWNER_DECISION_SOURCE=PR_256_COMMENT_5330399072
OWNER_DECISION_COMMENT_ID=5330399072
OWNER_IDENTITY=xuezhiorange-png
OWNER_ROLE=model_validation_owner_role
OWNER_ROLE_ATTESTATION=I_AM_ACTING_AS_MODEL_VALIDATION_OWNER_ROLE
OWNER_PROVENANCE=AUTHENTICATED_REPOSITORY_OWNER_EXPLICIT_INTERACTIVE_APPROVAL_2026-08-18
DECIDED_AT=2026-08-18T23:23:00+08:00
METRIC_CONTRACT_VERSION=v0.3-metric-contract-v1
METRIC_CONTRACT_AUTHORITY=docs/forecast-quality/s3-quality-metrics-contract.md
METRIC_BINDING_CONTRACT=docs/v0-3/s1/metric-coverage-and-quality-contract.md
METRIC_REGISTRY_COUNT=22

The owner decision accepts the prepared contract definition, canonical metric
identities, formulas/policies, and planning crosswalk only. The accepted value
is the contract version; it is not a metric result and is not a canonical
S1-METRIC-CONTRACT PASS.

## 3. Deterministic payload and SHA-256 replay

The repository precedent at
`docs/v0-3/s1/evidence/s1-data-quality-threshold-policy-decision.json`
defines the replay convention: UTF-8, uppercase keys as issued, sorted JSON
keys, compact `,` and `:` separators, SHA-256, and a hash scope that excludes
the self-referential `OWNER_DECISION_SHA256` field. The payload is constructed
from the owner comment's decision/governance fields; rendered GitHub HTML is
not hashed.

```text
OWNER_DECISION_HASH_REPLAY=PASS
OWNER_DECISION_PAYLOAD_BINDING=PASS
OWNER_DECISION_BINDING=PASS
OWNER_DECISION_SHA256=e3ff3221338863aa9128890c23e463e7a3868cd8dfc3e1b2c30c503c351a3acd
CANONICALIZATION_ENCODING=UTF-8
CANONICALIZATION_JSON_KEYS=SORTED
CANONICALIZATION_JSON_SEPARATORS=,:
CANONICALIZATION_PAYLOAD_KEY_CASE=UPPERCASE_AS_ISSUED
CANONICALIZATION_HASH_ALGORITHM=SHA-256
CANONICALIZATION_HASH_SCOPE=OWNER_DECISION_PAYLOAD_EXCLUDING_OWNER_DECISION_SHA256
```

The exact canonical payload, serialized with sorted keys and compact
separators, is:

```json
{"ACCEPTED_VALUE":"v0.3-metric-contract-v1","DECIDED_AT":"2026-08-18T23:23:00+08:00","DECISION":"ACCEPT","DECISION_ID":"S1_METRIC_CONTRACT_FREEZE_AND_ACCEPTANCE","DECISION_SCOPE":"FREEZE_AND_ACCEPT_CURRENT_PREPARED_METRIC_CONTRACT_DEFINITION_ONLY","METRIC_CONTRACT_AUTHORITY":"docs/forecast-quality/s3-quality-metrics-contract.md","METRIC_CONTRACT_VERSION":"v0.3-metric-contract-v1","METRIC_REGISTRY_BOUND":true,"METRIC_REGISTRY_COUNT":22,"OWNER_DECISION_FINAL":true,"OWNER_DECISION_READY_FOR_BINDING_AND_INDEPENDENT_REVIEW":true,"OWNER_IDENTITY":"xuezhiorange-png","OWNER_PROVENANCE":"AUTHENTICATED_REPOSITORY_OWNER_EXPLICIT_INTERACTIVE_APPROVAL_2026-08-18","OWNER_ROLE_ATTESTATION":"I_AM_ACTING_AS_MODEL_VALIDATION_OWNER_ROLE","PLANNING_ALIAS_CROSSWALK_ACCEPTED":true,"S1_METRIC_BINDING_CONTRACT":"docs/v0-3/s1/metric-coverage-and-quality-contract.md"}
```

## 4. Metric readiness remains separate from canonical acceptance

CURRENT_STATUS=OWNER_DECISION_ISSUED_REVIEW_REQUIRED
EXTERNAL_DECISION_REQUIRED=false
ACCEPTED_VALUE=v0.3-metric-contract-v1
OWNER_DECISION_ISSUED=true
POLICY_INDEPENDENTLY_REVIEWED=false
S1_METRIC_CONTRACT_CANONICAL_GATE_PASS=false
S1-METRIC-CONTRACT=BLOCKED
BLOCK_REASON=METRIC_CONTRACT_NOT_ACCEPTED
CANONICAL_GATE_COUNT=17
CURRENT_CANONICAL_GATE_PASS_COUNT=13
CURRENT_CANONICAL_GATE_BLOCKED_COUNT=4

The 22 metric identities remain bound to the existing authority and all remain
`NOT_ISSUED`: seven daily point metrics, four cumulative-season metrics, four
single-day peak metrics, four sustained-seven-day peak metrics, and
`P50_UPPER_COVERAGE`, `P80_UPPER_COVERAGE`, and `P90_UPPER_COVERAGE`.
Planning aliases remain distinct from canonical S3 IDs; `P80-P50` and `P90-P50`
remain planning spreads, not prediction-interval widths.

## 5. Unsatisfied execution facts and safety boundary

CURRENT_METRIC_EXECUTION_STATUS=NOT_EXECUTED
CURRENT_METRIC_RESULT_STATUS=NOT_ISSUED
CURRENT_S3_DAILY_ROWSET_CONTRACT_STATUS=NOT_AVAILABLE_FROM_CURRENT_S2_BINDING
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
CURRENT_P50_SEMANTICS_VERIFIED=false
CURRENT_P80_SEMANTICS_VERIFIED=false
CURRENT_P90_SEMANTICS_VERIFIED=false
QUANTILE_COVERAGE_COMPUTED=false
BASELINE_P80_P90_COMPUTED=false
BACKTEST_EXECUTED=false
MODEL_VALIDATION_EXECUTED=false
SOURCE_002_RAW_READ=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_DATA_ACCESS=false
EXTERNAL_HOLDOUT_ACCESS=false

No metric result is generated. No P50/P80/P90 semantics, daily-rowset
completeness, quantile coverage, baseline quantiles, model validation, or
backtest is claimed.

## 6. Canonical and lifecycle boundaries

ACCEPTANCE_RECORD_CHANGED=false
ACCEPTANCE_PACKAGE_CHANGED=false
CANONICAL_RECONCILIATION_CHANGED=false
CANONICAL_GATE_STATUS_MUTATION_COUNT=0
CANONICAL_GATE_BLOCK_REASON_MUTATION_COUNT=0
CANONICAL_CLOSEOUT_PERFORMED=false
INDEPENDENT_REVIEW_PERFORMED=false
READY_PERFORMED=false
MERGE_PERFORMED=false
NEXT_GATE_STARTED=false
V0_3_S1_COMPLETE=false
V0_3_S1_ACCEPTED=false
V0_3_S2_AUTHORIZED=false

The current-main 13 PASS / 4 BLOCKED count is a read-only governance-state
binding. This task does not change any canonical gate, acceptance record,
acceptance package, reconciliation artifact, metric authority, formula,
registry, split, holdout, or downstream gate.
