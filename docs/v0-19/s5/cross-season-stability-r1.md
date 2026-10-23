# V0.19 S5 cross-season stability research

Task: `V0_19_S5_CROSS_SEASON_STABILITY_R1`.
Base main: `aca2698201ff7296a8b5e1408bf0ac8822e06f8f`.
Owner instruction SHA256: `9f26ed9cab07ef25d5817f73f956ba2f8dcc34107104f7ffadd9e58654d43ae9`.
This instruction authorizes one bounded research branch, real diagnostics,
predictions and scoring, one Draft PR and one final exact-head CI. No new
approval infrastructure, production registration or deployment is introduced.

## Frozen method, before new evaluation

The only new candidate is `TWO_SEASON_CONSENSUS_SHRINK_V1`.
For each admitted Base, F1/F2 use its **entire authorized historical business
season**, July01 through April15, including the valid short terminal bin.
Actual kg/mu and baseline kg/mu use exactly the same dates, area and frozen
reference within the experiment. Both historical seasons use Fold B for the
final replay fit. This is matching arithmetic scope, NOT proof of physical
equivalence. Missing days are not filled.

`spread=abs(F1-F2)`, `weight=1/(1+spread)`,
`F_stable=1+weight*(F_original-1)`, Decimal precision 50.
`F_original` remains the original sealed S4 final Base coefficient fitted from
complete seven-day bins. Its raw pooled ratio, bin counts and shrinkage to the
global factor are reported separately from full-season F1/F2. No old estimator
or configuration changes. Without both complete legal seasons, or with a zero
baseline denominator, the new method returns exactly 1 (`BASELINE_FALLBACK`).

Experiment A is restricted to its 2023–2024 training data and Fold A. It cannot
use 2024–2025 labels to create the second factor; all its predictions therefore
equal the baseline. That equality is a fallback control, not validation of an
improved estimator. Experiment B uses the two historical training seasons and
Fold B. Exact source identities, not counts alone, determine their intersection.

Per-bin target mass is baseline micro-kg times F_stable, half-even rounded;
the existing largest-remainder allocator apportions this calibrated mass using
baseline daily weights, earliest date on ties. Both complete and terminal bins
preserve their **calibrated** mass. Zero-baseline bins remain zero. Full support
is generated once per Base, then H7/H15 are sliced without renormalization.

## Immutable sources and execution

Use only the previous S4 run `v0-19-s4-real-training-final-shPL7z` and the exact
historical files already pinned by `v019_real_training.PINS`. Original S4
training, fits, four-model curves, verification and comparison hashes are pinned
individually. None of those artifacts or old numerical modules are rewritten.
The old source identity is read from fixed S4 Git commit
`cc281c0650b2fb676ad3f3cb081a3affb4ce3b28`, never from a future worktree.
Missing historical objects fail validation; no historical hash is regenerated.

The prediction phase has no target-label/report input. Its input adapter selects
only the original fit's legal historical training seasons. Predictions and new
parameters are sealed on clean committed code, independently recomputed by a
separate process, and only then can the scoring phase open the fixed old report.
Real outputs are new private 0700 directories / 0600 files; existing paths fail.
The existing Owner-controlled retrospective execution convention is reused.

## Diagnostic accounting, not causal identification

Record training membership, reference, parameter identity, evaluation membership,
weights and physical basis as separate dimensions. A post-hoc training-sum audit
holds 2023–2024 rows fixed and changes only the reference denominator, then adds
2024–2025 training rows. This explains the arithmetic of the global ratio; it
does not score Fold B on the earlier validation season or claim a causal
generalization effect. Old fits and predictions remain sealed and unchanged.

Official S1 rolling-window metrics retain repeated day appearances and exactly
the old numerator, denominator and per-metric cohorts. Separately report unique
Base×day totals, over/underprediction, month/bin breakdowns, Base-equal WAPE and
Base contributions to the official error change. Overlapping origins are not
independent observations. Uncomputable cases and all C0 members remain visible.

Observed harm is the sum of positive per-Base absolute-error changes versus the
baseline; observed gain is the sum of negative changes. Their difference is
the net change. Compare both with the old volume model to quantify harm avoided
and improvement forgone. No tuned definition of "large degradation" is added;
show the continuous worst changes and all Base results instead.

Graphs use all actual computed values. Daily examples are the first common Base
by ID and the largest old volume H7 harm / gain (ID tie-break), explicitly
post-hoc illustrations only, never sample selection or parameter tuning.

All new candidate results are `EXPLORATORY`, including the already exposed
2025–2026 replay. Historical recorded inbound kg is not proven equivalent to
SOURCE_002 inbound net weight; historical area known_at remains unproven.
`RETROSPECTIVE_REPLAY`, `EXPOSED_HISTORICAL_BENCHMARK`, `STRICT_PIT=false`,
`PRODUCTION_ELIGIBLE=false`, `GENERALIZATION_ESTABLISHED=false`.
Full-season scoring is not admitted. No model promotion, Ready, Merge or Deploy.

## Reproduction

On the clean committed research branch, explicitly supply the previously
authorized artifact root and a new private output directory for each phase:

```sh
python -m backend.research.v019_stability_cli predict \
  --owner-task V0_19_S5_CROSS_SEASON_STABILITY_R1 \
  --artifact-root /absolute/authorized/artifact-root --output /absolute/new-run/a
python -m backend.research.v019_stability_cli verify \
  --owner-task V0_19_S5_CROSS_SEASON_STABILITY_R1 \
  --artifact-root /absolute/authorized/artifact-root --a /absolute/new-run/a \
  --output /absolute/new-run/verification
python -m backend.research.v019_stability_cli score \
  --owner-task V0_19_S5_CROSS_SEASON_STABILITY_R1 \
  --artifact-root /absolute/authorized/artifact-root --a /absolute/new-run/a \
  --verification /absolute/new-run/verification --output /absolute/new-run/b
```

`verify` is a separate process that recomputes the candidate parameters, curves,
inventory and seal, without target labels. Before opening the fixed old report,
`score` checks that receipt, recomputes again and rejects incomplete predictions.
It verifies the original four methods' complete metric objects and cohorts,
not rounded WAPE alone. Private output manifests record UTC execution intervals,
process IDs, command, code Git SHA, source identity and output file SHA256.
Do not commit those real row-level outputs. The output directories must not
already exist; an existing artifact is never overwritten.

The final private report includes the required JSON/Markdown/HTML plus seven
data-hashed SVG figures. Full member lists, zero-actual exclusions, per-metric
numerators, denominators, Base coverage and NC reasons remain in JSON. Shared
A/B Base identities are compared separately inside B; they do not control the
different seasons' actual weights or physical-source uncertainty.
