# Candidate 01 parameter-calibration manifest v1

This artifact freezes the finite Candidate 01 validation neighborhood before
any validation evaluation is started. It is control-plane evidence only; it
does not change the incumbent model, authorize production parameter changes,
or open TEST.

```text
TASK_ID=V0_3_S4_C01_PARAMETER_CALIBRATION_MANIFEST_AND_CONTROLLED_VALIDATION_R1
BASE_MAIN_SHA=39f63206a07b70e08b2602fca61f4d077b2ed362
PR583_MUST_BE_IN_BASE=true
EXPERIMENT_PLAN_VERSION=v0.3-experiment-plan-v1
EXPERIMENT_PLAN_HASH=9e223a02a1b38c028c230a45eb1fa8323f3c2247bb85e7b439f3351e51042500
GUARDRAIL_POLICY_VERSION=v0.3-s4-guardrail-policy-v1
GUARDRAIL_POLICY_HASH=74ecd47339572955e654cf61c38ee6b0546ba51a36e67f80f6ad4dd4519f1ff8
CANDIDATE_ID=01_parameter_calibration
CANDIDATE_FAMILY=PARAMETER_CALIBRATION
PARENT_MODEL_ID=V0_2_CURRENT_MODEL
CANDIDATE_01_PARAMETER_MANIFEST_VERSION=v0.3-s4-c01-parameter-manifest-v1
CANDIDATE_01_PARAMETER_MANIFEST_HASH=eba8af27f926635d654aa4c5331f323a9e4edfa399659e1917b729ac6550910b
```

## Incumbent authority

The manifest binds the complete snapshot loaded from
`configs/maturity_curve.yaml`.

```text
INCUMBENT_CONFIG_FILE_SHA256=fc023976a228c36556ed5f7ababe722a3dd8a558ed11e0473eb415b52dd69ace
INCUMBENT_CONFIG_HASH=3571477d5822f57cd2c424620915560e22481f48983b397a1f1b8934e1a7612c
model_family=shared_spline_partial_pooling
random_seed=20260624
curve.spline_degree=3
curve.spline_knot_count=6
curve.ridge_alpha=0.10
pooling.full_pooling_sample_target=4
```

The only permitted parameter paths are:

```text
curve.spline_knot_count
curve.ridge_alpha
```

Every other incumbent value, including model family, seed, spline degree,
pooling, offset, holiday, interval, forecast, production-plan, expected-yield,
marketable-rate, phenology, harvest-efficiency, weather-response, and residual
features, is immutable for this candidate. Native floats are forbidden in the
canonical candidate snapshots; Decimal values are serialized by the existing
repository canonicalizer.

## Exact four-run registry

| Run | `curve.spline_knot_count` | `curve.ridge_alpha` | Random seed | Parameter manifest hash | Candidate config hash |
| ---: | ---: | ---: | ---: | --- | --- |
| 1 | 5 | 0.10 | 20260624 | `fbf5335e98981a7161e16230495760c46a02b96ac0151b557e999428380273ec` | `78805778135e84a76a7a08656f42f0f74337f4166d82bf7dfb31e01e4a36daa8` |
| 2 | 7 | 0.10 | 20260624 | `811cb73f3471ab7b9743e31b1d0458009d5c4d5348a2dd722e54fd1af45dc754` | `ca6b3857c3c5a8f316283bdfb4e3b97530a1aba9597120e6b46cf82c75c5a3b9` |
| 3 | 6 | 0.05 | 20260624 | `924b520bceac3a577f447ebda7247cd4083f522075293a97260a2f716509c529` | `5345b04f6bb2926b2a0f3a45b06d9ffc8e449291605ee7d50899e2d2c875cae5` |
| 4 | 6 | 0.20 | 20260624 | `3706c05b1ff5128d69ff8bece5a5c17808ff25354e0d2ca83e7a2ad9deb3df38` | `1240bbd568a9eb87a689b88c09053e5fe7c5a559df4f8b1aa970cad513cf71da` |

The run 4 candidate config hash is fixed by the canonical manifest evidence as
`1240bbd568a9eb87a689b88c09053e5fe7c5a559df4f8b1aa970cad513cf71da`.

The four ordinals are sequential and exhaustive. No fifth configuration,
adaptive insertion, retry, post-validation substitution, or candidate from
another S4 family is authorized by this manifest.

## Execution and ledger boundary

Phase A implements the manifest verifier, derived-config builder, S4-B gate
adapter, and append-only invocation journal. A durable `EVALUATION_STARTED`
event must precede any model evaluation and counts toward the validation
budget even if no terminal event is later written. Existing events cannot be
overwritten or deleted. This task authorizes no automatic retry, manual retry,
or operator rerun.

The required paired identities are resolved from durable current authority
before the first run. No placeholder or synthetic hash is acceptable. The
historical S3 closeout currently records that the incumbent daily forecast
authority was not durably retained; if that remains the first non-derivable
authority, the runner must stop before writing any STARTED event.

```text
MAX_VALIDATION_EVALUATIONS=32
MAX_RUNS_PER_CANDIDATE=4
PLANNED_TOTAL_RUN_COUNT=32
ACTUAL_VALIDATION_EVALUATION_COUNT=0
CURRENT_LEDGER_ROW_COUNT=0
AUTOMATIC_RETRY_AUTHORIZED=false
MANUAL_RETRY_AUTHORIZED=false
OPERATOR_RERUN_AUTHORIZED=false
TEST_EVALUATION_AUTHORIZED=false
TEST_REMAINS_SEALED=true
S4_CANDIDATE_EXPERIMENT_EXECUTED=false
PRODUCTION_PARAMETER_CHANGE_AUTHORIZED=false
S4_MODEL_CHANGE_AUTHORIZED=false
SELECTED_CANDIDATE_ID=NOT_ISSUED
MODEL_APPROVED_FOR_PILOT=false
```

The manifest freezes the experimental neighborhood; it does not select a
winner, promote a parameter value, release V0.3, or imply any next step.

## Phase A verification

```text
CANDIDATE_01_FREEZE_COMMIT_SHA=33511af91e558f355991189cc551e85c2fae32a6
PHASE_A_FORMAT_CORRECTION_COMMIT_SHA=45bf4519ea0baae858d67b38624467fd388cbe4f
PHASE_A_EXACT_HEAD_CI_RUN=34178189758
PHASE_A_EXACT_HEAD_CI_HEAD_SHA=45bf4519ea0baae858d67b38624467fd388cbe4f
PHASE_A_EXACT_HEAD_CI=SUCCESS
CANDIDATE_01_EXECUTION_PREFLIGHT=BLOCKED
FIRST_NON_DERIVABLE_AUTHORITY=HISTORICAL_INCUMBENT_DAILY_FORECAST_AUTHORITY
CANDIDATE_01_EXECUTION_BLOCK_REASON=HISTORICAL_INCUMBENT_DAILY_FORECAST_AUTHORITY_NOT_DURABLY_RETAINED
ACTUAL_VALIDATION_EVALUATION_COUNT=0
CURRENT_LEDGER_ROW_COUNT=0
NO_VALIDATION_EVALUATION_STARTED=true
```

The official preflight produced no journal file and no `EVALUATION_STARTED`
event. The result is recorded separately in the controlled-validation
workpaper and evidence; no validation result or candidate metric is inferred.
