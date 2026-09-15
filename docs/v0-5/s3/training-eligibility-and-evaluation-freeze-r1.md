# V0.5-S3 training eligibility and evaluation freeze R1

`V0_5_S3_TRAINING_ELIGIBILITY_AND_EVALUATION_FREEZE_R1` freezes the sample
contract before any S3 model fit or S4 weather-ablation work.  It is an audit
and evaluation-design deliverable.  It does not train a model, generate a
weather feature, or authorize an experiment.

## Decision

The current active Base Registry contains 39 active identities.  The accepted
ERA5-Land fact layer intentionally covers the 38 `YUNNAN_CORE` bases.  The one
remaining Registry identity, `乡丰蓝莓基地` (`base_36bc109841061a7798ed99a3`), is
explicitly `OUT_OF_YUNNAN`; it is retained in the Registry and excluded from the
Yunnan weather join.  This is a scope reconciliation, not a fuzzy match or a
Registry mutation.

The three authorized historical sources are treated as complete exports at the
source level, and the confirmed active-source ledger-zero semantics are used:
an active source day with an absent farm ledger entry is represented only when
the reviewed ledger marks it as `OBSERVED_OR_AUTHORIZED_LEDGER_ZERO`.  A global
no-record day remains `UNKNOWN_GLOBAL_NO_RECORD`.  Calendar days before a
source's coverage start are `SOURCE_NOT_COVERED`; they are not zero-filled.

The strict business calendar is July 1 through April 15, inclusive, in the
`Asia/Shanghai` business interpretation.  April 16 and later are outside the
business label domain and are not pulled back into it.

## Requalified current evidence

The audit was replayed from the hash-pinned private Base Registry and reviewed
base ledger.  It produces 117 base-season candidates:

| result | count |
| --- | ---: |
| strict complete | 0 |
| partial | 82 |
| blocked | 35 |
| full-season total-label eligible | 0 |
| full-season yield-label eligible | 0 |
| peak-label eligible | 0 |

The zero strict count is an evidence result, not a model-training blocker for
this planning task.  The current data supports a separate known-support
research layer: 17,795 known base-day labels across 72 base-season pairs.  The
remaining 16,057 business-calendar base-day cells are unknown, including
global no-record days and source-start margin days.  Known-support metrics must
never be reported as full-season totals, yield, peak, or complete curve scores.

Global no-record days are 31 in 2023–2024, 8 in 2024–2025, and 40 in
2025–2026.  Source-start margin days are 25, 0, and 21 respectively.  The
resulting peak domain is incomplete for all 117 base-season pairs.

Known-support rolling origins remain separately auditable: 16,160 complete W7
origins and 15,323 complete W15 origins.  They are not independent full-season
samples and cannot upgrade the season-level label.

## Frozen evaluation contract

- Primary unit is `BASE`; farm membership is metadata for attribution and
  aggregation only.
- Primary aggregation is base-equal macro.  A separately labelled kg-weighted
  WAPE may be reported as a scale diagnostic.
- A forward time split is required: earlier season(s) to a later season.  An
  optional out-of-base split holds out whole canonical bases.
- Randomly shuffling adjacent days is forbidden.  Overlapping origins are not
  counted as independent base samples.
- Peak ties select the earliest date.
- `W7(D)` is `D+1..D+7`; `W15(D)` is `D+1..D+15`.  The complete window must stay
  inside the same business season and every label in the window must be known.
- A zero denominator is `NOT_COMPUTABLE`, never a fabricated zero score.
- No absolute business threshold is invented in this freeze; the observed
  sample counts and proposed decision dimensions are the decision inputs for a
  later coordinator review.

The common comparable set is model-independent and requires the same eligible
label domain for every model being compared.  The extended coverage set is a
known-support research diagnostic only.

## Weather join boundary

The accepted ERA5-Land daily fact snapshot is feasible for the 38-base
`YUNNAN_CORE` scope: exact Base IDs and all 868 business-calendar dates per
base are present.  Weather is checked only for join feasibility in S3.  It is
not used to improve label eligibility, and no weather feature is generated.
Climate-zone mapping remains unfrozen and is not an authority for this audit.

ERA5-Land remains `REANALYSIS_REFERENCE`; historical as-issued forecast PIT is
not established.  That unresolved operational replay authority does not change
the S3 historical-label contract.

## Reproducible command

Run from the repository root with explicit private roots:

```sh
.venv/bin/python -m scripts.audit_v0_5_s3_training_eligibility_r1 \
  --config configs/v0_5_s3_training_eligibility_r1.json \
  --registry-root "$BASE_REGISTRY_S1_FINAL" \
  --weather-root "$ERA5_FINAL_REPLAY_1" \
  --output "$S3_ARTIFACT_ROOT/replay-1"
```

Run the same command with a new output directory for `replay-2`, then compare
the two private outputs:

```sh
.venv/bin/python -m scripts.report_v0_5_s3_training_eligibility_r1 \
  --first "$S3_ARTIFACT_ROOT/replay-1" \
  --second "$S3_ARTIFACT_ROOT/replay-2" \
  --output "$S3_ARTIFACT_ROOT/replay-comparison.json"
```

The accepted local replay used the private artifact root
`blueberry-area-yield-artifacts/s3-training-eligibility-r1-accepted-v2/`.
Its two output directories are private and contain no raw XLS files.  The
artifact manifest hash is
`7832d0418377253fc8709c29793b90a7b3085759c09247288aedadab96161df1`, and the
replay comparison reports `deterministic_replay=true`.

## Immutable boundaries

No R1–S2 historical artifact was modified.  No model training, weather feature
generation, S4 ablation, database schema change, API change, MCP change, or
deployment was performed.  S3 model training remains unauthorized until a
separate coordinator decision uses this frozen qualification and evaluation
contract.
