# V0.3 version closeout and acceptance reconciliation R1

## 1. Final decision summary

V0.3 is **CLOSED** under the coordinator's explicit closeout authorization. Its bounded real-business empirical forecast capability is PASS. S1–S3 are complete; S4 is closed without an admissible replacement. S5/S6 are not entered, TEST remains sealed, and weather is excluded.

This closeout is a documentation-only reconciliation submitted for coordinator review. It is not Ready/Merge authorization, a release/tag, model approval, or a claim that all originally contemplated or future features are complete. Prior evidence remains unchanged.

## 2. Current main identity

Base main and PR #607 merge commit: `f3a0804869d459d423b31115ff9aae8a31ab0996`.
Fresh fetch and GitHub PR metadata confirmed #607 MERGED. The closeout branch starts at this exact main. Migration `backend/alembic/versions/0033_empirical_maturity_authority.py` exists on main; this task does not run it.

The [machine-readable evidence](evidence/v0-3-version-closeout-and-acceptance-reconciliation-r1.json) binds immutable source-file SHA-256 values. PR607 R5's historical OPEN_DRAFT field describes its original execution snapshot; current merged status comes from GitHub, not rewriting that snapshot.

## 3. Completed V0.3 capabilities

For the verified Banna/Dx acceptance scope, the following are PASS: core forecast, real input binding and execution, empirical maturity authority, daily forecast, harvest state, mature inventory state, single-day peak, canonical seven-day peak, persistence, query/readback, and deterministic hashing.

[S1 acceptance](s1/evidence/s1-acceptance-record.json), [S2 completion](s2/evidence/s2-slice-complete-registry-closeout.json), and [S3 closeout](s3/evidence/s3-final-closeout-and-s4-entry-authorization-r1.json) establish their respective COMPLETE states. S3 completion is engineering/terminal acceptance, not historical PIT metric success: those historical metrics remain NOT_COMPUTABLE. The later empirical capability does not recover missing historical production forecasts.

## 4. PR #607 first-real-forecast acceptance

Source: [merged R5 execution evidence](forecast-operational-acceptance/evidence/banna-empirical-first-forecast-r5.json). This task does not rerun the forecast or probe current runtime availability.

| Accepted fact | Value |
| --- | --- |
| Scope | 版纳勐旺农场 / 勐旺加工厂 / Dx / 736.000000 mu |
| Quantity semantics | arrival = harvest |
| Historical source SHA-256 | `a55cbf259f52e6a20e30d646b43d2aa0f104f60786d725dbc051e46c76b390d5` |
| Historical/calibration total | 968113.233000 kg |
| Calibration denominator / yield | 736.000000 mu / 1315.371240 kg/mu |
| Forecast period / rows | 2026-10-15 through 2027-05-09 / 207 |
| Forecast total | 968113.233000 kg |
| Single-day peak | 2027-04-28 / 15117.032000 kg |
| Canonical 7-day rolling cumulative peak | 2027-04-26 through 2027-05-02 / 88757.236000 kg |

R5 proves empirical authority, Task9 materialization, normal forecast execution, persistence, fresh-session readback/hash parity, mass balance, capacity constraints and arrival/harvest identity. These are no longer capability blockers. Yield is acceptance baseline calibration, not historical agronomic truth. Marketable and realization factors are explicit neutral baseline policies, not observed rates.

The empirical path uses a historical harvest calibration proxy, not a fabricated Task8 spline artifact or physiological maturity truth. Its accepted complete-ledger zero-day convention does not change S4 sparse-horizon missing-day policy. This is a non-production acceptance runtime and a bounded capability proof.

## 5. S4 final disposition

[Final S4 authority](s4/evidence/s4-incumbent-retention-final-closure-r1.json) remains `CLOSED_NO_ADMISSIBLE_REPLACEMENT_SELECTED`. Selected candidate is NOT_ISSUED, count 0; `V0_2_CURRENT_MODEL` is retained. Retention is not selection or pilot approval.

PR607 does not overturn candidate dispositions, recover C04 selection evidence, establish a new S4 winner, or validate model accuracy. No experiment plan or candidate execution is authorized.

## 6. TEST / validation-budget disposition

TEST remains SEALED, with no access or evaluation. No database connection/readback or budget mutation occurs in this closeout.

Budget source: [accepted C04 durable evidence](s4/evidence/s4-c04-controlled-real-validation-r1.json), SHA-256 `78b1489b28fe0056e1c7fd88165f927c04d16bf1083926048ba4c36e3c1498b3`.

```text
BUDGET_STATE_CLASS=LAST_ACCEPTED_DURABLE_BUDGET_SNAPSHOT
DURABLE_BUDGET_READBACK_AVAILABLE=false
VALUES_ARE_CURRENT_DATABASE_READBACK=false
VALUES_ARE_LAST_ACCEPTED_DURABLE_SNAPSHOT=true
LEGACY_RECONCILED_VALIDATION_DEBIT=4
LAST_ACCEPTED_CANONICAL_STARTED_COUNT=4
LAST_ACCEPTED_EFFECTIVE_CONSUMED=8
LAST_ACCEPTED_REMAINING=24
REMAINING_VALIDATION_BUDGET_UNUSED=24
VALIDATION_BUDGET_DELTA=0
```

Unused budget is not authorization to spend it or carry it into another experiment.

## 7. S5/S6 disposition

[Post-S4 entry authority](s5/evidence/s5-post-s4-closure-authority-realignment-r1.json) remains unchanged: MODEL_APPROVED_FOR_PILOT=false and S5_ENTRY_STATUS=BLOCKED_NO_PILOT_APPROVED_MODEL. S5/S6 are NOT_ENTERED; implementation has not started.

Their historical slice definitions remain recorded, but this version ends without entering them. This task neither reclassifies the S5 requirement audit nor authorizes proposed S5-A/B/C. Real forecast execution cannot substitute for pilot model approval.

## 8. Explicit V0.3 out-of-scope list

The following are OUT_OF_SCOPE_OR_FUTURE_VERSION, not newly scheduled tasks:

- WEATHER_FORECAST
- WEATHER_MODEL
- MULTI_FACTORY_ROUTING
- AUTOMATIC_FACTORY_ALLOCATION
- AUTOMATIC_PEAK_SHAVING
- TRANSPORT_OPTIMIZATION
- NEW_MODEL_EXPERIMENT
- NEW_S4_CANDIDATE
- MODEL_RETRAINING
- S5_PILOT_OPERATIONS
- S5_FRONTEND_EXPANSION
- S5_ADOPTION_RECORDS
- S6_REAL_SEASON_PILOT_ACCEPTANCE
- PRODUCTION_RELEASE

## 9. Weather exclusion

V0_3_WEATHER_IN_SCOPE=false. Weather integration, modeling, calibration and weather-driven forecast are all false. Existing Task9 weather schema/configuration and the neutral multiplier 1.000000 mean only SCHEMA_COMPATIBILITY_OR_NEUTRAL_BASELINE. They do not establish weather capability. No weather work is automatically handed to the next version.

## 10. Known limitations

The empirical baseline replays historical shape. P50=P80=P90 has UNCERTAINTY_STATUS=NOT_CALIBRATED_IDENTICAL_POINT_SCENARIOS: neither P80 nor P90 coverage is validated. Multi-season generalization is not proven; model pilot approval, real-season business pilot and production release are absent.

These are explicit limits of the closed version, not reasons to expand its scope or claim every original business-pilot aspiration was delivered.

## 11. Future-version handoff

Only a separately authorized coordinator decision may open a NEW_MODEL_EXPERIMENT or NEXT_FORECAST_VERSION. No concrete next-version number, feature scope, weather inclusion, implementation task, or budget transfer is defined here. The existing capabilities and provenance are reusable subject to that future authorization.

## 12. Final machine-readable verdict

```text
V0_3_VERSION_STATUS=CLOSED
V0_3_CORE_FORECAST_CAPABILITY=PASS
V0_3_FIRST_REAL_BUSINESS_FORECAST=PASS
V0_3_S1_STATUS=COMPLETE
V0_3_S2_STATUS=COMPLETE
V0_3_S3_STATUS=COMPLETE
V0_3_S4_STATUS=CLOSED_NO_ADMISSIBLE_REPLACEMENT_SELECTED
V0_3_MODEL_APPROVED_FOR_PILOT=false
V0_3_S5_STATUS=NOT_ENTERED
V0_3_S6_STATUS=NOT_ENTERED
V0_3_TEST_STATUS=SEALED
V0_3_WEATHER_IN_SCOPE=false
V0_3_NEW_MODEL_EXPERIMENT_AUTHORIZED=false
V0_3_CLOSEOUT_COMPLETE=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
FINAL_STOP_GATE=COORDINATOR_V0_3_VERSION_CLOSEOUT_R1_REVIEW
```

Validation for this documentation-only package: JSON parsing, source/reference binding, append-only pointer and path-allowlist checks, and git diff whitespace checks. No forecast, database operation, pytest/full suite or accuracy evaluation is required or claimed.
