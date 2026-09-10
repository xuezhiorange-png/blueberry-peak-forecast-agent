# Workpaper — C04 controlled real validation R1

## Scope and authorization

This workpaper covers only the explicit authorization in
`V0_3_S4_C04_CONTROLLED_REAL_VALIDATION_R1`: four serial historical SOURCE-002
VALIDATION invocations for `04_yield_parameter`. The frozen multipliers were
not recomputed, reordered, adaptively selected, or reused for another run.

The controlled adapter bound every STARTED event to
`0394d63d83d78d95064689d0c0e58c652d4db8df`, the frozen run manifest hash, the
V2 experiment plan, and the V3 sparse guardrail surface. The durable
PostgreSQL preflight supplied candidate counts and effective budget state;
there was no JSONL or documentation-counter fallback.

## Data and leakage boundary

The official SOURCE-002 partition identities were verified before execution:

```text
MATERIALIZED_DATASET_IDENTITY=f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785
TRAIN_ROWS=16224
TRAIN_CONTENT_SHA256=be2d4184434a0f389af21c315945322e9216cd17cc471b772e3fff389d3386d2
VALIDATION_ROWS=8006
VALIDATION_CONTENT_SHA256=4cbf1119f83034464159210ebbbeea5ec87848f92ce044bb328949a8f5331d06
EVALUATION_TARGET_ROWS=688
FORECAST_HORIZONS=7,14,21
```

Before each candidate prediction, validation target quantities were masked.
Only after the prediction identity was fixed were the frozen VALIDATION actuals
attached for metric computation and guardrail evaluation. The paired incumbent
was created with the same source, cutoff, target identities, horizons, grain,
and metric contract and was not recorded as a fifth STARTED event.

No TEST bytes, TEST rows, TEST labels, or TEST predictions were read.

## Result interpretation

All four scorer callbacks completed and all four terminal events were
persisted. The V3 evaluator reported primary and point comparisons, quantile
coverage, and data-quality evidence. The complete-window metrics remained
explicit diagnostics, as required by the sparse surface. The existing minimum
comparable-row rule for required breakdown axes was also enforced; it produced
`BELOW_MINIMUM` and therefore no run was eligible.

The run result is consequently `C04_VALIDATION_OUTCOME=BLOCKED`, not PASS,
FAIL-as-model-selection, or a promotion decision. There is no best run and no
TEST authorization in this workpaper.

## Ledger evidence

The eight persisted events are four immutable STARTED/terminal pairs. Their
global canonical ordinals are 1 through 4. Every STARTED carries
`NORMAL_RUN`, the same execution code SHA, its frozen run manifest hash, and
the expected CAS state. Final durable readback is:

```text
LEGACY_RECONCILED_VALIDATION_DEBIT=4
CANONICAL_STARTED_COUNT=4
C04_CANONICAL_STARTED_COUNT=4
EFFECTIVE_CONSUMED=8
REMAINING=24
BUDGET_DELTA=4
RETRY_COUNT=0
```

The machine-readable event hashes, metric identities, per-run budget states,
and final authority head are in the accompanying evidence JSON. This task
stops at coordinator review; it does not Ready or Merge the PR.
