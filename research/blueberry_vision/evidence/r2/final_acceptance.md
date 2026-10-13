# R2 engineering acceptance

TASK_ID=BLUEBERRY_VISION_R2_OFFLINE_DETECTION_COUNTING_PIPELINE

Engineering acceptance: PASS (synthetic only).

- M0: fresh repository/source/main/worktree/authorization checks; R1 regression69 PASS.
- M1: genuine bounded PNG/JPEG decode, EXIF/RGB, bytes/dimensions/hash, secure local roots;
  independent R2 schema2.0.0 and unchanged original R1 files.
- M2: deterministic56 PNG images plus masks, 14 per split, 14 real pixel scenes, final
  ownership/visibility-based GT and explicit hidden/ignored/zero counts.
- M3: actual classical RGB components, boxes and counts; config frozen before test.
- M4: real CPU NumPy logistic fit,14 train images/16,800 pixels/80 steps, saved JSON model,
  reloading and held-out inference. Loss0.6931471805599452 to0.10966382100196519.
- M5: independent matching/AP/count evaluation; hand-computed goldens; full subgroup,
  coverage and failures; two models compared over the same28 test/OOD frames.
- M6: COCO controlled roundtrip, real overlays and self-contained HTML; actual browser
  model switching/filter/layers/draw/edit/delete/export checked with immutable GT.
- M7:271 tests PASS, including69 R1 and202 new, zero skip/error/failure; Ruff lint/format
  PASS and mypy25 source files PASS. Two fresh56-image run-demo executions PASS; all270
  generated artifact identities match across output directories and frozen M4/M5 results
  reproduce exactly. Full run artifact hash46bf083a841ef17418f4063869f1589b04637a276b2ed99f8ab3915251c3af60.

| Synthetic-only metric | A classical | B trained |
| --- | ---: | ---: |
| Precision |0.9606986899563319|0.959051724137931|
| Recall |0.7787610619469026|0.7876106194690266|
| F1 |0.8602150537634409|0.8649173955296404|
| Research all-points AP50 |0.750849467917799|0.762991750187723|
| Count MAE |4.142857142857143|3.9285714285714284|
| Count Bias |−3.7142857142857144|−3.5|
| TP/FP/FN |440/18/125|445/19/120|
| Error images retained |11|12|

Count unit: visible_fruit_per_image. AP is not COCO mAP. No real accuracy or kg proof.
All negative cases are preserved, not replaced by selected successful examples.

## Evidence and persistence

Actual output: test_results.json, e2e_acceptance.json, independent_review.json,
browser_review.json, r1_real_experiment_gate.json, source_integrity.json, configs/models/
predictions/metrics/comparison JSON, image_evidence_index.json and known_limitations.md.
All stage checks preserve actual stdout/exit codes in mN_checkpoint.json. M0–M6 were
already committed/pushed individually; M7 receives its own ordinary commit/push and
remote-HEAD verification. Final SHA cannot be embedded in its own artifact seal.

artifact_manifest.json in this evidence directory seals the evidence snapshot before
m7_checkpoint.json. research/blueberry_vision/artifact_manifest.json seals the complete
persisted research index including M7 checkpoint/progress, original R1 files, code,
schemas, examples and evidence, excluding its own seal. Ignored caches/temp datasets
are excluded. The workflow's own hash is recorded in source_integrity.json.

Remote CI and Draft PR are inspected after M7 push; their exact final HEAD/run/jobs/
URLs and actual conclusions are recorded in the persistent GitHub Draft PR and final
receipt. This local document does not claim remote CI passed before observing it.
The new path-isolated workflow checks actual head, research tests/static checks and
both committed and newly generated artifact bytes; existing repository CI is unchanged.

## Boundaries and next authorization

REAL_IMAGE_ACCURACY_VALIDATED=false
REAL_BLUEBERRY_MODEL_APPROVED=false
VISUAL_YIELD_KG_CALIBRATED=false
PRODUCTION_DEPLOYMENT_APPROVED=false

No private/real orchard images, production DB or current-season actual were read.
No Harvest State, production forecast, API/MCP/Dashboard, production lock or frozen
V0.15–V0.18 files were changed. No pretrained weights or real dataset were downloaded.
Ready/Merge/Tag/Release/Deploy remain unauthorized.

Recommended next task: separately authorized small real-image collection/annotation
pilot, visibility and candidate class confirmation, canonical identity and near-frame
grouping, independently sealed cross-base/date/device field test and fixed evaluation.
Any yield/weight experiment additionally needs authorized independent weighing,
sampling coverage and point-in-time calibration. See known_limitations.md for gaps.
