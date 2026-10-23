# V0.19 S4 real training and four-model evaluation

Task: `V0_19_S4_REAL_TRAINING_AND_FOUR_MODEL_EVALUATION_R1`.
Base main: `82b3781b4f19c7ba76792abdd552987ee746deeb`.
The Owner's current instruction grants the bounded historical research fit,
prediction and scoring operations below. This is the existing local
`OWNER_CONTROLLED_RETROSPECTIVE` execution mode. No new approval or signature
system is introduced. Original S3/S4 artifacts remain historical snapshots.

## Source admission

`v019_real_training.py` reads only explicit relative files in the supplied
controlled artifact root. Every source workbook, S1/S4/S6 authority, original
Fold A/B profile and registry is checked against its frozen SHA256. No model
pickle, production database, current-season source or discovery scan is used.

The exact original XLS identities are
`8fa003b4abdea0b0bd9c50a9fbd619ad15ea5c9a2e790faa5e5b3353a2a01d20`
and `f4ffba4b10a3129c768871bc5f3dfa2845534bc0e7eb04e166ba97211fa92dd6`.
The existing hash-verified source characterization identifies `入库公斤数`, KG,
with dates and source farm/subfarm labels. This supports recorded-inbound-weight
conditional research. It does not establish equivalence to field harvest or
the SOURCE_002 net-weight definition. No transport or commodity-yield factor
is applied. Unknown weight events/units are rejected by the adapter.

The 37 S6 candidates mean 15 + 22 **Base-seasons**, covering 26 distinct Bases.
Each is joined by exact Base/season/source identity to historical area in mu,
the complete business calendar and accepted source-member identities. Daily
amounts reconcile to S6 totals. Duplicate keys, conflicting/missing dates,
changed weights, unknown/partial days, wrong area/source and unresolved members
are rejected. All 78 training Base-seasons remain in the disposition ledger,
including the 41 S6-ineligible entries and their original reasons.

Both zero-authority paths are retained: S6's newly authorized no-record zero,
and the unchanged legacy `REUSED_UNCHANGED_MEMBERSHIP_ZERO`. The latter requires
the original ledger's confirmed-zero status and authority. Missing days are
never filled. Mixed historical authority CSVs are hash-checked bytewise, then
projected to 2023–2024/2024–2025 before numeric quantity selection. No 2025–2026
quantity from those mixed ledgers enters fitting.

Normalized daily rows, exact source members and full seven-day bins each receive
their own hashes. A raw workbook hash is never presented as a normalized-rowset
hash. July01 anchors all bins; partial season-end bins remain in the exclusion
inventory. Fit manifests retain dates, area, source hashes, normalized weights,
profile identity, configuration, parameters and training-code identity.

## Two temporal experiments, unchanged estimators

* Experiment A: 2023–2024 fit, 2024–2025 validation, using the **existing Fold A**
  reference. The Fold B reference contains the validation season and is not used
  for this temporal validation.
* Experiment B: same fixed estimator structure, refit on the two historical
  training seasons; fixed Fold B baseline and S2 for the 2025–2026 exposed replay.

The numerical bodies of `VOLUME_CALIBRATION_V1` and `VOLUME_TIMING_V1` are shared
with the existing synthetic interface. Shrinkage 4, one uniform shape pseudo-bin,
Decimal arithmetic and exact micro-kg allocation remain unchanged. Synthetic
interfaces continue rejecting REAL. The real adapter rechecks the actual pinned
files and recomputes the expected fit before accepting parameters. A dictionary
claiming REAL or containing expected hash strings cannot replace file checks.

The two experiments have distinct fit identities. Their sorted training bins
must precede their respective evaluation seasons. No random date/window split,
2025–2026 fit, parameter search or model selection from evaluation is performed.
The multiplicative quantity model cannot create mass in a zero-baseline bin;
the timing layer redistributes only the calibrated bin mass.

## Execution and isolation

Use a clean, committed, locally tested checkout. The CLI records actual UTC
start/completion, process ID, command, Git SHA, source identity and current Owner
task authorization. It does not backdate issuance. Output paths must be new;
directories are 0700 and files 0600.

```sh
python -m backend.research.v019_real_training_cli predict \
  --owner-command V0_19_S4_REAL_TRAINING_AND_FOUR_MODEL_EVALUATION_R1 \
  --artifact-root /ABSOLUTE/EXISTING/AUTHORIZED/ARTIFACT_ROOT --output /NEW/RUN/a
python -m backend.research.v019_real_training_cli verify \
  --owner-command V0_19_S4_REAL_TRAINING_AND_FOUR_MODEL_EVALUATION_R1 \
  --artifact-root /ABSOLUTE/EXISTING/AUTHORIZED/ARTIFACT_ROOT --a /NEW/RUN/a \
  --output /NEW/RUN/verification
python -m backend.research.v019_real_training_cli score \
  --owner-command V0_19_S4_REAL_TRAINING_AND_FOUR_MODEL_EVALUATION_R1 \
  --artifact-root /ABSOLUTE/EXISTING/AUTHORIZED/ARTIFACT_ROOT --a /NEW/RUN/a \
  --verification /NEW/RUN/verification --output /NEW/RUN/b
```

Prediction uses complete support before H7/H15 slicing, without window refits or
actual-quantity normalization. Experiment B preserves the exact 19,032 original
C0 members and 39 Bases. Complete curves, window hashes/peaks and failure records
are sealed. A separate process re-reads pinned sources and recomputes both fits
and all predictions. Scoring checks these again before opening the frozen S3
2025–2026 label report. Prior S4 report hashes are checked in this later phase.

The shared S1 arithmetic supplies all ten metrics, common per-metric cohorts,
numerators, denominators, failures and zero-peak exclusions. The new comparison
keeps all four methods on the same computable cohort. Failed predictions retain
their C0 membership and the independent full-C0 actual-mass denominator. Any
incomplete prediction comparison is marked blocked with no overall winner;
conditional metric subsets cannot hide coverage loss. Original real baseline/S2 fractions match the
sealed S3 report exactly. Reports retain all Bases, seen/unseen fallback results,
actual prediction examples and improvements/degradations. Repeated cohort lists
are stored once with resolvable hash references, without dropping members.

Private outputs include `training-manifest.json`, `fitted-models.json`,
`predictions.json`, verification, `comparison.json`, `report.md`, `report.html`
and execution manifests. Real rows, areas, parameters and reports are not uploaded
to GitHub. The PR contains code, synthetic tests and this implementation note.

The research remains `RETROSPECTIVE_REPLAY`, `EXPOSED_HISTORICAL_BENCHMARK`,
`STRICT_PIT=false`. Historical available_at/issuance and area known_at remain
unproven. H7 has one rolling-seven window; its zero start error is structural.
Full-season WAPE stays not computable. No blind, production-accuracy, promotion
or deployment claim follows from these results.
