# R3 frozen pixel inference and independent reference evaluation

`evaluation.py` runs the existing R2 algorithms on the R3 asset-only contract. It
does not change R1/R2 schemas, invent a synthetic flag for a photograph, retrain a
model, fetch weights, or access a production service.

## Frozen baselines and input adapter

`freeze_r2_baselines(output_path=None)` verifies the saved R2 configurations,
detector/evaluator source files, trained model seal and model-file SHA256. It
records both algorithm identities, train-only provenance, original training image
IDs and dataset hash, dependency versions, source hash, protocol hash and the R3
adapter. No image label is required to freeze or infer.
The freeze also hashes R3's ingestion, asset contract, annotation qualification
and split/seal helper source files; changing those helpers invalidates the freeze.

* A: `RGB_threshold_and_4_connected_components_v2`, unchanged R2 RGB thresholds.
* B: `CPU_NumPy_logistic_pixel_classifier_v2`, unchanged synthetic-trained 80-step
  logistic model. Artifact SHA256 is
  `b685ff32fac8542e3f50bbbb5f5a1b09d2319114ce14af17078de06ac9482b10`.

The pre-registered adapter limits the longest EXIF-normalized RGB edge to 1280,
preserving aspect ratio with Pillow LANCZOS and never upscaling. This lets larger
real photographs satisfy the original R2 four-million-pixel bound. Boxes are
mapped back to the original EXIF-normalized RGB half-open XYXY frame; normalized
coordinates are also retained. The adapter hash and each image's actual resize
geometry remain in the prediction evidence. Changing the adapter or R2 thresholds
is rejected; the real test cannot be used to select either.

R2 pixel candidates retain their original class label as provenance, then map
explicitly to `CANDIDATE_VISIBLE_BLUEBERRY`. This is a research label adaptation,
not an approved orchard label, maturity standard, or weight measurement.

## Pixel-only execution

`run_real_inference(dataset, data_root, freeze, model_key="A", image_ids=None,
output_path=None, ledger_dir=None)` validates the independent R3 manifest and its
source permissions, opens bounded authorized PNG/JPEG bytes with the secure R3
wrapper around R2's decoder, verifies source/preprocessing hashes, and calls R2's
pure-pixel functions. The signature has no GT/annotation parameter. The strict
asset manifest contains no objects or reference counts. No filename/seed/count
lookup determines an output.
When original dimensions, EXIF orientation and coordinate-frame metadata exist,
inference compares them with the actual hash-bound decoded metadata. Re-sealing
a wrong declaration cannot bypass this check. Legacy absence remains unknown.

Each image retains its source purpose and raw asset hash, success/failure reason,
candidate boxes/scores, visible candidate count, preprocessing and stable
prediction hash. A decoding failure has null objects/count, never zero. The
bundle binds the complete dataset, prediction scope, model/config/freeze hashes
and `gt_consumed=false`. Predictions are immutable when written.

## Admission, seal and scoring sequence

1. Freeze the configuration and append `CONFIG_FROZEN` to an immutable research
   exposure ledger.
2. Run each baseline on image pixels and persist predictions. When a ledger is
   provided, inference appends `PREDICTIONS_FIXED` after the artifact exists.
3. Build explicit group-aware TEST/OOD assignments and a test seal, preserving the
   asset and annotation versions. Published labels are exposed public benchmark
   labels, not a newly unseen blind test.
4. `evaluate_real(dataset, predictions, annotations, split, test_seal,
   freeze=freeze, ledger=ledger_directory)` appends `GT_SCORE_READ` before the
   first reference-geometry validation, then delegates admission to `splits.py`.
5. Any missing/unqualified reference, source failure, seal/config mismatch or
   exposure-order failure prevents an accuracy claim. All scope failures remain
   visible. A qualified subset is not silently selected to improve scores.

Only explicit TEST/OUT_OF_DOMAIN members of the sealed admission scope can be
scored. Predictions for TRAIN, VALIDATION or UNASSIGNED are retained as excluded
rows with `NOT_IN_EVALUATION_SPLIT`; they cannot enter TP/FP/FN, AP or count error.
The report exposes `evaluation_image_ids` and their separate scope hash. A mixed
TRAIN/VALIDATION/TEST golden tests this boundary even when all three have labels.
Every sealed TEST/OOD image omitted from inference receives a per-image
`PREDICTION_MISSING` exclusion and remains in the failure list with a null count.
An incomplete test prediction scope blocks aggregate accuracy rather than silently
scoring a selected subset. Coverage distinguishes raw annotation availability,
qualified reference availability, absent predictions and decoding failures.

An in-memory dict or append-only file ledger is an integrity mechanism, not
independent GT custody, an authenticated reviewer identity, or production access
control. The snapshots' documented human/publisher provenance is still required
for a real benchmark. Simulated SEALED reviews can only score the explicitly
synthetic engineering path.

## Metric meanings

R2 `match_boxes` performs same-image, same-class, score-ranked one-to-one matching
at IoU 0.5. Duplicate predictions produce FP. Unmatched predictions sufficiently
inside IGNORE/UNCERTAIN rectangles use R2's intersection-over-prediction-area 0.5
ignore rule. Raw predicted counts still include every emitted candidate, so
ignored detections are not silently removed from count errors. Reference counts
include TARGET objects only. This policy is explicit and versioned.

The compact report contains TP/FP/FN, Precision/Recall/F1, per-image matched IoUs,
signed/absolute count error, MAE/Bias, over/under-count totals, empty-image false
positives, evaluated/excluded/missing/failed coverage, all failures and density,
occlusion, lighting, size/domain subgroup rows. Unknown scene metadata stays
UNKNOWN; a stratum with no supported images has null accuracy, not zero error.
Counts use `visible_fruit_per_image` and are not converted to kilograms.

`RESEARCH_AP50` is one-class VOC all-points precision-envelope AP with no maxDets
cap. It is not COCO mAP. Hand-computable tests prove TP/FP/TP AP = 5/6, duplicate
penalties, same-image matching and errors [-2, 3, -1] yielding MAE 2/Bias 0.

The optional official `pycocotools==2.0.11` adapter executes `COCOeval(...,"bbox")`
with maxDets [1,10,100] and reports separately `COCO_MAP50` and
`COCO_MAP50_95`. It records the actual version/limits and refuses unsupported
ignore-region semantics rather than silently changing reference policy. Golden
engineering fixtures check perfect and fully missed references; these are not
real blueberry scores. If the library/version is unavailable it reports NOT_RUN.
If no qualified GT exists, both COCO and research accuracy remain NOT_EVALUABLE
with null values even when the library is installed.

The R2 dependency-only CI can still run all research engineering tests without
pycocotools: only the three dedicated official-COCO goldens skip when the optional
package is absent. The R3 pinned-dependency path runs those goldens fully.

## No-reference photographs

Public licensed photographs without documented per-fruit GT can be decoded and
inferred. They cannot supply accuracy, count error or a fake zero reference. The
report preserves model counts, failure reasons and coverage while all accuracy
fields remain null. Public external, authorized orchard and synthetic purposes
never aggregate into one accuracy scope. Public-photo inference proves adapter
execution, not orchard accuracy or commercial model approval.

The final task evidence determines whether any real reference was available;
this implementation and its synthetic regression tests do not create one.
