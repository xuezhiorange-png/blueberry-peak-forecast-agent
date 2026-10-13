# R2 synthetic detection and visible-count evaluation

`evaluator.py` evaluates generated reference boxes and sealed prediction bundles. It
does not load production data, train a model, or treat predictions as annotations.
Its scope is **SYNTHETIC DEMONSTRATION — NOT REAL BLUEBERRY ACCURACY**. A visible
count has unit `visible_fruit_per_image`; it has no conversion to kg or approved
maturity grades. R1's real-experiment gate continues to reject these samples.

The public entry points are `bbox_iou`, `match_boxes`, `evaluate_predictions`,
`default_evaluation_config`, and `compare_reports`. The CLI `evaluate` consumes
the generator's dataset manifest and a detector's prediction bundle. The default
scope is `test` plus `out_of_domain`; an explicit split list can evaluate train or
validation separately. Images outside the selected evaluation scope are not
counted, while unknown image IDs and malformed records are rejected. No output is
truncated to 100 detections, including the high-density pressure scene.

## Reference and artifact integrity

The evaluator verifies manifest, per-image prediction, and bundle canonical
hashes; dataset binding; the common seven-identity `dataset_split_hash`; and an
optional prediction-scope hash. It verifies unique image and reference object
IDs, positive image dimensions, finite half-open XYXY coordinates inside the image,
nonempty class labels, normalized candidate scores in `[0,1]`, and equality of
declared counts with the number of boxes. A normalized score may be explicitly
nonprobabilistic; its magnitude is used only for ranking. Optional box image IDs
must match the containing image. Invalid geometry, sources, counts, hashes, scene
field types, or inference states raise explicit `ValueError` reason codes rather
than becoming zero counts.

These checks establish artifact integrity. They cannot prove that an upstream
algorithm used pixels, that a source has business authority, or that an annotation
is correct. Those properties are checked separately by asset, detector, isolation,
and authorization tests. The supplied manifest must be synthetic, and real records
are rejected by this evaluator version. Each reference record must separately
retain `SYNTHETIC=true`, source authority with `synthetic_only` permission and its
split listed in allowed uses, and (for complete GT) `synthetic_reference`
annotation quality. A sealed manifest does not permit a model prediction to be
relabelled as reference or an unauthorized record to become usable. This is a
declared-provenance gate, not independent verification of business authority.

## Matching and detection metrics

Bounding-box IoU is intersection area divided by union area. Coordinates describe
continuous half-open rectangles; edge contact has zero overlap. For each image,
predictions are processed by descending score, with original input order retained
on score ties. Each prediction can match the highest-IoU unmatched reference of
the same class at the frozen IoU threshold. Equal-IoU references retain reference
order. Every reference is consumed at most once. Duplicate predictions become FP;
unmatched references become FN. Optional ignored regions suppress an unmatched
prediction if intersection divided by prediction area is at least the locked
ignore threshold. A valid reference match takes precedence over ignoring.

Precision is `TP/(TP+FP)`, Recall is `TP/(TP+FN)`, and F1 is
`2TP/(2TP+FP+FN)`. A zero denominator yields null and a reason code. Empty reference
images are valid and remain in coverage and count evaluation; missing annotations
are distinct from reference count zero.

The implementation reports `bbox_ap50_research_all_points`, **not COCO mAP**.
For every supported class, it sorts predictions across the evaluated images by
descending score and then stable image and prediction indices. It rematches
same-image reference boxes at IoU 0.50, constructs the cumulative precision/recall
curve, makes the backward maximum precision envelope, and integrates over each
recall increment (VOC all-points interpolation). The reported mean averages only
classes with reference support. Classes without GT have null AP and are listed;
supported classes with no predictions have AP zero. The evaluator config binds
AP method, AP IoU, operating IoU, ignore policy, unit, and `max_detections=null`.
It records evaluator version and the hash of evaluator source bytes. This differs
from COCO's 101-point integration and maxDets convention and does not implement
COCO mAP50:95.

## Count errors, failures, and strata

For every evaluable image, signed error is `pred_count-gt_count` and absolute
error is its magnitude. MAE averages absolute error; Bias averages signed error.
Positive Bias means overcount. Total overcount and undercount sum the positive
and negative signed-error magnitudes respectively. Empty-image false-positive
count is the raw output-box count on evaluable zero-reference images.

Ignored unmatched predictions are excluded from detection FP **but retained in
the raw count**. The synthetic reference includes only defined visible objects
and excludes ignored/unobservable objects. A model that predicts in ignore
regions can consequently have a count error while that box is not a detection
FP. Both results are exposed; the evaluator never edits a model's count using GT.

Missing GT, missing prediction records, and failed inference are excluded from
the metric denominator and retained as complete per-image coverage rows. Their
errors are null. Rows also retain independent inference status and reason so a
missing-GT image with failed inference does not hide the inference failure.
`excluded_count` counts rows once; `missing_count` and `failed_count` describe
different causes and may overlap. No evaluable images produces
`NOT_EVALUABLE`, null MAE/Bias/AP, and `NO_EVALUABLE_IMAGES`.

Density, occlusion, lighting, size, domain, empty/nonempty, and scene-type metrics
are recomputed from their own per-image rows and confidence-ranked curves. The
predeclared strata remain present even with no samples and report null error with
`NOT_EVALUABLE`. Missing dimension values are reported as `unknown`; present
dimensions must be strings except the boolean `empty` flag. Every failed,
missing, false-positive, false-negative, or nonzero-count-error row is preserved
in `failure_cases`; no difficult image is silently removed.

`compare_reports` requires identical manifest, split, scope, evaluator config,
image rowset, and reference hashes. It computes candidate-minus-baseline MAE and
Bias differences on the common evaluable rows and lists each coverage gap. A
positive MAE delta is a worse candidate. Different coverage is never passed off
as improvement on the full scope. The comparison does not assert candidate B is
superior and does not establish production accuracy.

## Independent Golden checks

`tests/test_r2_evaluator.py` was written before the evaluator. Its manually
computable examples include IoU `1/3`, duplicate predictions with ranked
AP `5/6`, cross-image nonmatching with AP `1/4`, wrong classes, empty/no-output
images, ignored regions, and all 101 targets without truncation. For predicted
counts `[2,1]` versus references `[3,0]`, errors `[-1,+1]` independently give
MAE `1`, Bias `0`, overcount `1`, and undercount `1`. Another stratified case gives
errors `[-1,+2]`, MAE `1.5`, Bias `0.5`, and separate subgroup errors `1` and `2`.
Missing and failed rows, malformed metadata, binding changes, count tampering,
configuration hashes, and negative comparisons are also exercised.

Run the evaluator tests with:

```bash
python -m pytest research/blueberry_vision/tests/test_r2_evaluator.py -q
ruff check research/blueberry_vision/evaluator.py research/blueberry_vision/tests/test_r2_evaluator.py
mypy --explicit-package-bases research/blueberry_vision/evaluator.py research/blueberry_vision/tests/test_r2_evaluator.py
```

The final milestone evidence records the actual test output and actual synthetic
dataset results. These specifications are not a claim of real image validation,
business model approval, confidence intervals, or production deployment readiness.
