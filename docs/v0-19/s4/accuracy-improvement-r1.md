# V0.19 S4 — quantity and timing research, R1

Task: `V0_19_S4_FORECAST_ACCURACY_IMPROVEMENT_R1`.
Reviewed main: `b97ff7bca3ae883e07bae5ffe38455f9773823e5`.
This is an independent research extension, not a production model replacement.
Owner's current S4 instruction authorizes these two models; the historical S2
single-candidate experiment and its results are not rewritten.

## Method freeze and temporal separation

The following one quantity estimator and one timing extension are fixed before
any new-model real fit or scoring. No parameter search is implemented.

* `VOLUME_CALIBRATION_V1`: on admitted complete seven-day training bins compute
  pooled actual kg/mu divided by pooled baseline kg/mu. A Base-specific ratio
  is shrunk toward that global factor with `n/(n+4)`, where n is complete-bin
  count. Unseen Bases/zero baseline denominators use the global factor.
  This is multiplicative calibration: zero baseline mass remains zero, a known
  inability to create production where the frozen baseline predicts none.
* `VOLUME_TIMING_V1`: extend that **same** calibrated quantity with the mean
  training-bin normalized daily shape, with one uniform pseudo-bin. Fit excludes
  zero-actual bins from shape estimation, but never excludes them from quantity
  calibration/evaluation. Restrict the fixed seven-position shape to partial
  support bins, then apportion exactly the calibrated bin mass.
* Bin target rounds half-even to integer micro-kg. Largest exact rational
  remainder, earliest date on ties; Decimal precision 50 for fitting. No float
  business arithmetic. H7/H15 slice complete generated support; no window refit.
* Each training bin carries exact source hash, Base, area, season and dates;
  incomplete/duplicate/nonfinite/negative data fails. Fit dates must precede
  the evaluation season. Sorted training input, fitted config and source-row
  identity are sealed. Predict has no evaluation-label argument.
* Synthetic experiment: fit 2023, evaluate 2024, reuse the identical locked fit
  on 2025. No refit/search based on validation or exposed-test results. Three
  fictional Bases deliberately retain improvement, deterioration and zero-label
  outcomes. Four methods use the same joint computable cohort and original S1
  `_errors`, `_add`, `_finish`; the original strict PIT public scorer is unchanged.

This numerical research API is not a new authority/signature system. Real fit
is currently rejected, not enabled by a caller-supplied boolean or relabeling
of a real source manifest. The real diagnostic CLI accepts only three pinned
S3 artifacts. No public CLI loads arbitrary training labels.

## Training source review (do not confuse historical stages)

| Source | Confirmed public evidence | Remaining admission boundary |
|---|---|---|
| 2023–2024 original source | SHA `8fa003b4abdea0b0bd9c50a9fbd619ad15ea5c9a2e790faa5e5b3353a2a01d20` | Physical event dictionary, source-to-current-label comparability and precise lawful fit-row manifest not verified for this fit |
| 2024–2025 original source | SHA `f4ffba4b10a3129c768871bc5f3dfa2845534bc0e7eb04e166ba97211fa92dd6` | Same; cannot silently use later-season rows to validate a profile already fitted on them |
| V0.5 Fold B | 2023–24 + 2024–25; 9,131 known daily training rows, 25 Bases; 14 natural OOB Bases in evaluation | Known support is not a complete-season claim; historical issuance/available_at not established |
| V0.8 S1/S4 | Exact seasonal identity; later retrospective area authority covers 117 Base-seasons | Area business confirmation does not prove historical known_at |
| V0.8 S6 | **15 and 22** complete training Base-seasons; 37/78 eligible under that frozen authority | Supersedes earlier zero-eligible quantity finding; 41 remain blocked. Does not itself prove physical equivalence or present training-row admission |
| Current S3 SOURCE_002 | 39 Bases, 80 included farms, 4 study exclusions, 9,906 Base-days; H7 9,672/H15 9,360 | Recorded inbound net weight; not automatically total field harvest. Exposed benchmark, non-strict PIT |

References (read as immutable historical evidence):
`docs/v0-5/s3/known-support-no-weather-baseline-evidence-r1.json`,
`docs/v0-8/s1/cross-season-identity-authority-application-and-canonical-dataset-rebuild-r1.md`,
`docs/v0-8/s4/user-confirmed-three-season-area-authority-application-r1.md`,
`docs/v0-8/s6/no-record-zero-semantics-and-season-total-rebuild-r1.md`,
`docs/v0-19/s1/peak-metrics-and-experiment-protocol-r1.md`.
Historical code identity is the fixed main SHA above, not a mutable worktree hash.
No original evidence or expected hash was changed.

**Real new-model fit/comparison: BLOCKED_TRAINING_SOURCE_ADMISSION.** This does
not assert historical training data is absent or all incomplete. It means this
run has not established an exact compatible early-fit/later-validation bundle.
The current task explicitly permits completing runnable models and synthetic
tests while retaining this limitation. No extra private training directory was
scanned, no evaluation weight was used for fitting, no real training executed.
`NO_BLIND_HOLDOUT_AVAILABLE`; 19,032 overlapping windows are not independent.

## Real diagnostics

The CLI verifies the pinned S3 phase-A bytes, recomputes its seal with the
unchanged original engine, verifies its separate-process receipt, then reads
the pinned report. Neither original predictions nor labels are altered.

All 39 Bases are ranked, not filtered on performance. Unique Base-day totals
and per-mu quantities are separate from overlapping-window S1 WAPE denominators.
Per-bin `|sum(p-a)|` is a lower bound on `sum|p-a|`; its residual is explicitly
**not** a causal timing component. Monthly groups are calendar phases, not
observed biological phenology. Lead and tail-window diagnostics are retained.
H7 rolling7-start zero is structural. Full-season WAPE stays not computable.

Private outputs: `analysis.json`, `comparison.json`, `report.md`, `report.html`,
five representative actual/predicted SVG curves (top three, median, last error
contribution ranks), numerical WAPE/peak chart, synthetic E2E JSON and manifest.
Plots use floats only for pixel coordinates. Actual business values stay Decimal.
New-model real metrics are null/BLOCKED, never synthetic substitutes.

Run against **only the existing explicitly authorized S3 output directory**:

```sh
python -m backend.research.v019_accuracy_study \
  --s3-root /ABSOLUTE/AUTHORIZED/S3_RUN \
  --output /ABSOLUTE/NEW_PRIVATE_S4_RUN
pytest -q backend/tests/area_yield/test_v0_19_s4_accuracy.py
```

Output directory must not exist. Existing exclusive writer uses directory 0700,
files 0600; no source file is modified. No raw business rows or real report goes
to GitHub. Current code/source hashes belong in the private run manifest;
CI and PR SHA are recorded separately and never inherited from S3.

The two research models and synthetic temporal comparison are implemented.
Real S3 error diagnostics are computed; reliable real new-model gain is **not
established**. Capacity-planning use remains conditional scenario research,
not production accuracy. Base is not factory; no factory assignment is invented.
No promotion, deployment, automatic Ready/Merge, or S4 formal-completion claim.
