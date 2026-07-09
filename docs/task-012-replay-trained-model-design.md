# TASK-012 replay_trained_model design freeze

Status: DESIGN DRAFT
Scope: Task 12 design only
Base main: `863fb4c59c653dbdbe84b094c2c4afdaa953aa87`

---

## 1. Purpose

TASK-012 freezes the design contract for `Task10ModelPolicy.REPLAY_TRAINED_MODEL` under rolling forecast / retrospective replay.

The existing repository already contains the enum value `replay_trained_model`, but current replay binding intentionally rejects it. This design defines what must be true before that policy can be implemented safely.

This document does **not** authorize implementation. It only freezes the future contract, boundaries, identities, anti-leakage rules, and test expectations for a later implementation slice.

---

## 2. Prior deferral binding

Earlier TASK-011 Phase 4 amendments explicitly kept Task 10 `replay_trained_model` out of scope:

- Phase 4a deferred Task 10 `replay_trained_model` to a later independent design decision.
- Phase 4b excluded Task 10 `replay_trained_model` from metric-formula work.
- Phase 4c explicitly deferred Task 10 `replay_trained_model` to a later independent design decision.
- Phase 4c-3 explicitly marked Task 10 `replay_trained_model` as deferred / do-not-touch.

TASK-012 is that independent design decision. It does not retroactively widen Phase 4a / 4b / 4c / 4c-3.

---

## 3. Current-state contract

Current production behavior remains valid until a separate implementation PR lands:

1. `Task10ModelPolicy.HISTORICALLY_AVAILABLE_MODEL` is the only replay-authorized Task 10 model policy.
2. `Task10ModelPolicy.REPLAY_TRAINED_MODEL` must continue to be rejected by the existing replay binding path.
3. No caller may silently fall back from `replay_trained_model` to `historically_available_model`.
4. No caller may silently fall forward from `historically_available_model` to `replay_trained_model`.
5. Any implementation PR that changes this behavior must include a dedicated contract-test slice first.

---

## 4. Definition: replay-trained model

A replay-trained model is a Task 10 residual model artifact trained inside a retrospective replay using only data that would have been visible at the replay node's effective forecast cutoff.

It is not:

- a current production model selected by latest timestamp;
- a model trained with full-season hindsight;
- a model trained once outside the replay and then treated as if it were historically available;
- a model whose training labels, features, Task 8 outputs, Task 9 outputs, or Task 10 residual labels include information not visible at the replay node cutoff.

The replay-trained model is a replay artifact. Its validity is scoped to the replay attempt, replay node, scenario, cutoff, and training manifest that produced it.

---

## 5. Authority and anti-leakage model

### 5.1 Cutoff authority

Every replay-trained model must bind to an explicit `forecast_cutoff_at` and a derived `training_cutoff_at`.

- `forecast_cutoff_at` is the replay node's effective decision time.
- `training_cutoff_at` is the latest timestamp at which all training inputs, labels, and upstream artifacts must have been historically visible.
- `training_cutoff_at` must be less than or equal to `forecast_cutoff_at`.
- If label latency rules require a stricter cutoff, `training_cutoff_at` must encode that stricter value.

### 5.2 Feature visibility

Training features may only use upstream source rows whose authority timestamp or local availability date is visible under the existing TASK-011 availability registry.

No feature query may use:

- wall-clock `now()`;
- latest-row selection;
- most-recent artifact selection;
- post-cutoff Task 8 / Task 9 / Task 10 outputs;
- future observed arrivals, harvest-state outputs, or residual labels.

### 5.3 Label visibility

Training labels must be selected from observed outcomes whose label availability is less than or equal to `training_cutoff_at`.

A label may have an observation date earlier than the cutoff and still be invalid if its authoritative availability timestamp is after the cutoff.

### 5.4 Upstream replay binding

Prediction with a replay-trained model must continue to bind to the replay-produced Task 9 harvest-state row for the current replay. Cross-run substitution remains forbidden.

The accepted Task 9 binding identity is:

- `task9_run_id` = replay-produced `HarvestStateRun.id`;
- `task9_result_hash` = replay-produced harvest-state result hash loaded through the integrity loader;
- `is_replay = TRUE`;
- `replay_code_version` and `replay_executed_at` from the replay attempt.

---

## 6. Identity model

A replay-trained Task 10 model artifact must expose a stable identity. The identity must be enough to reproduce, audit, and reject cross-run substitution.

Required identity fields:

- `model_policy = "replay_trained_model"`;
- `task12_policy_version`;
- `replay_attempt_id`;
- `replay_node_id`;
- `forecast_cutoff_at`;
- `training_cutoff_at`;
- `training_manifest_hash`;
- `training_dataset_hash`;
- `model_artifact_hash`;
- `model_config_hash`;
- `model_code_version`;
- `random_seed` or deterministic seed derivation rule;
- `task8_curve_identity` if Task 8 features are consumed;
- `task9_replay_binding_identity` if Task 9 replay outputs are consumed;
- `task10_training_run_id` if persisted in the Task 10 store;
- `task10_prediction_run_id` if the artifact is immediately used for prediction.

A replay-trained artifact is not canonical unless all identity fields are present and all hash fields are non-empty.

---

## 7. Training manifest contract

Every replay-trained model must write or persist a training manifest before prediction is accepted.

The manifest must include:

1. replay identity: attempt id, node id, scenario id, execution mode;
2. cutoff identity: forecast cutoff, training cutoff, timezone assumptions;
3. dataset identity: source tables / artifact ids, row counts, filters, excluded rows, and label availability rules;
4. feature identity: feature names, feature versions, upstream artifact hashes, visibility rules;
5. label identity: target definition, label availability timestamp, observation date semantics;
6. model config: algorithm family, hyperparameters, seed, deterministic serialization version;
7. artifact identity: model artifact hash, canonical payload hash, manifest hash;
8. blocker inventory: all skipped rows or blocked inputs with structured reason codes;
9. provenance: code version, policy version, created-by replay node, non-authoritative runtime timestamp.

The manifest hash must be computed from canonical content. Runtime timestamps that are not part of historical authority must not change the canonical hash.

---

## 8. Selection and reuse policy

### 8.1 Explicit policy request

`replay_trained_model` may only run when the caller explicitly requests `Task10ModelPolicy.REPLAY_TRAINED_MODEL`.

Implicit selection is forbidden.

### 8.2 No fallback

If replay training fails, the system must not silently fall back to a historically available model.

If no replay-trained artifact exists for the exact replay identity, the system must block with a structured blocker.

### 8.3 Reuse scope

A replay-trained model may be reused only when all of the following match exactly:

- replay attempt id;
- replay node id or explicitly frozen reuse group;
- forecast cutoff;
- training cutoff;
- training manifest hash;
- model config hash;
- model code version;
- Task 8 / Task 9 / Task 10 upstream identities;
- policy version.

Cross-run reuse is forbidden unless a future design amendment defines a separate promotion mechanism.

### 8.4 Coexistence with historically available model

`historically_available_model` and `replay_trained_model` are mutually exclusive model-selection policies for a single prediction execution.

A comparison run may evaluate both policies, but it must do so through separate prediction runs with separate identities and separate artifacts.

---

## 9. Blocker / failure taxonomy

A future implementation must expose structured blockers rather than generic exceptions.

Required blocker categories:

- `task12_replay_training_not_authorized` — implementation is not enabled or policy gate is closed;
- `task12_training_cutoff_invalid` — training cutoff is missing, after forecast cutoff, or violates label-latency rules;
- `task12_training_input_not_visible` — a feature, label, or upstream artifact is not historically visible at the cutoff;
- `task12_training_dataset_empty` — no training rows remain after visibility filtering;
- `task12_training_dataset_unstable` — canonical row ordering or dataset hash is not deterministic;
- `task12_model_artifact_hash_mismatch` — serialized model hash does not match manifest;
- `task12_manifest_mismatch` — manifest fields disagree with canonical artifact content;
- `task12_cross_run_substitution` — model, Task 9 binding, or prediction run belongs to another replay attempt;
- `task12_forbidden_implicit_fallback` — latest/current/most-recent fallback was attempted;
- `task12_training_execution_failed` — deterministic training failed after all inputs were valid.

A later implementation may map these to existing blocker enums if doing so preserves all semantic distinctions.

---

## 10. Audit and observability contract

Every replay-trained training attempt must emit an audit record.

The audit record must include:

- requested policy;
- accepted policy;
- replay identity;
- training cutoff;
- training manifest hash;
- model artifact hash;
- prediction run id, when produced;
- blocker code and blocker payload, when blocked;
- no-leakage validation summary;
- deterministic serialization version.

Audit records must be queryable by replay attempt and by model artifact hash.

---

## 11. Test contract

The first implementation-facing PR after this design must be a contract-test PR.

Required tests:

1. `REPLAY_TRAINED_MODEL` remains rejected before implementation gate is enabled.
2. Explicit `REPLAY_TRAINED_MODEL` does not fall back to `HISTORICALLY_AVAILABLE_MODEL`.
3. Training rows after `training_cutoff_at` are excluded.
4. Labels with post-cutoff availability timestamps are excluded even when their observation date is before the cutoff.
5. Empty training set produces a structured blocker.
6. Cross-run model artifact substitution is rejected.
7. Cross-run Task 9 replay binding substitution is rejected.
8. Identical replay inputs produce identical training manifest hashes and model artifact hashes.
9. Changing model config changes the model config hash and model artifact hash.
10. JSON / manifest mismatch for replay-trained artifact identity is rejected.
11. Prediction produced with replay-trained model carries `model_policy = "replay_trained_model"`.
12. Historically available and replay-trained comparison runs produce separate prediction identities.

No implementation PR may be considered complete until these tests exist and pass.

---

## 12. Implementation slice boundaries

This design freezes the following future sequence:

### Slice A — contract tests only

Allowed: tests for policy gate, no-fallback, cutoff leakage, cross-run substitution, deterministic hashes.

Forbidden: production implementation.

### Slice B — training manifest and identity plumbing

Allowed: manifest schema, identity projection, deterministic hash helpers, structured blockers.

Forbidden: live training algorithm changes unless contract tests already exist.

### Slice C — replay training execution

Allowed: deterministic training invocation under replay only, behind explicit policy gate.

Forbidden: changing Task 8 / Task 9 semantics, using current-data fallback, or changing historical model behavior.

### Slice D — prediction binding and artifact verification

Allowed: prediction path consumes exact replay-trained artifact identity and exact replay-produced Task 9 binding.

Forbidden: cross-run reuse or silent fallback.

### Slice E — API / CLI exposure if separately authorized

Allowed only after Slices A-D are green and a separate API / CLI amendment opens that surface.

---

## 13. Out of scope

This TASK-012 design PR does not authorize:

- production code changes;
- test changes;
- migrations;
- frontend work;
- API endpoint changes;
- CLI changes;
- model algorithm changes;
- new training jobs;
- branch cleanup;
- issue state changes;
- comments on existing PRs / issues;
- any modification to Task 8 / Task 9 / Task 10 semantics;
- any modification to TASK-011 Phase 4a / 4b / 4c / 4c-3 contracts.

---

## 14. Stop conditions

Future implementation must stop and return to design if any of these are encountered:

1. replay training requires post-cutoff labels or features;
2. deterministic artifact hashes cannot be reproduced;
3. the training dataset depends on wall-clock time;
4. an implementation needs to change Task 8 / Task 9 semantics;
5. a model artifact cannot be bound to exact replay attempt and node identity;
6. `historically_available_model` behavior would change;
7. current/latest/most-recent fallback is required to make the implementation pass;
8. API / CLI behavior must change before core replay training is proven;
9. a database migration is needed before the schema gap is separately authorized.

---

## 15. Final design position

TASK-012 may proceed only as design freeze first, then contract tests, then implementation slices.

The repository must continue to reject `replay_trained_model` until the policy gate, manifest identity, anti-leakage checks, deterministic artifact hashes, and replay binding tests are implemented in later authorized PRs.

> End of TASK-012 design freeze. No implementation. No tests. No migrations. No API / CLI / frontend changes.
