# R3 internal integration contract

All modules live in `research.blueberry_vision.r3`. Use R2 `r2_common.JSONDict`,
canonical hashes, strict read_json, immutable write_json_new and seal/verify_seal.
R2 files, contracts, images and artifact seals are not rewritten. No production
imports/DB/current-season actual. CLI is `python -m research.blueberry_vision.r3.cli`.

Dataset schema3.0.0 has `dataset_id`, `dataset_version`, `purpose` (exactly
PUBLIC_EXTERNAL_BENCHMARK/AUTHORIZED_ORCHARD_PILOT/SYNTHETIC_ENGINEERING), `SYNTHETIC`,
`sources` snapshots, `images` records, `manifest_hash`. No GT objects in the asset
manifest. Each image has image_id, asset_ref, asset_sha256, rgb_sha256, image_width,
image_height, preprocessing_version/hash, source_id, license reference/status,
nullable observed_at, UNKNOWN capture-time status, unresolved base identity,
nullable variety/session/sampling/video/frame/parent/known-fruit-multiview/source-batch
associations. Unknown association values never join every unknown image together.
Import batch is distinct from a known source collection batch. No file mtime as capture.

Sources may use license_status=LICENSE_VERIFIED and research_use=true; UNKNOWN/
LICENSE_UNVERIFIED is rejected. Synthetic uses explicit synthetic authority. Model
training and redistribution permissions remain independent and license conditions
and attribution are preserved. No silent permission upgrades.

Ingestion APIs in ingestion.py/contracts.py/dedup.py:
`import_images(data_root, source_index, registry, output_dir, ...) -> dataset`
`load_manifest(path) -> dataset`, `validate_manifest(dataset)`,
`audit_images(dataset,data_root) -> report`,
`find_near_duplicates(dataset,data_root,threshold=6) -> report`.
Commons source_index currently has images[{source_id,image_id,asset_ref,
asset_sha256,image_width,image_height,...}], purpose, dataset_id/version, SYNTHETIC.
Downloaded originals remain under /tmp/blueberry-r3-public-pilot until a reviewed
public sample/export policy explicitly permits repository redistribution.

Annotations in annotations.py are separate snapshots keyed image_id/source_asset_hash,
version/hash/label-definition/status/source/purpose, objects[{object_id,class_label,
bbox_xyxy,disposition TARGET/IGNORE/UNCERTAIN}], nullable visible_count for unannotated.
Candidate target label is CANDIDATE_VISIBLE_BLUEBERRY, never approved maturity.
Functions import_annotations/export_coco, create_draft, compare_annotations,
transition_review, adjudicate_annotations provide real executable equivalents.
R3 offline asserted reviewer IDs have identity_authenticated=false. Simulated
reviews never admit real accuracy. Qualified publisher GT requires actual documented
human annotation evidence/versions; public GT is EXPOSED_PUBLIC_BENCHMARK.

Splits in splits.py: `build_split(dataset, assignments, duplicate_report, ...)`;
`seal_test(dataset,split,annotations,freeze,...)`; `check_admission(...)`.
Graph associations and pending near-duplicate edges cannot cross splits; groups are
transitive. Defaults UNASSIGNED, never random adjacent-frame division. Immutable
freeze includes algorithm/config/model/training/protocol hashes before inference.
Seal records exposed public GT, and is integrity control rather than access control.

Inference/evaluation in evaluation.py: `freeze_r2_baselines(...)`,
`run_real_inference(dataset,data_root,freeze,...)` has NO GT parameter/read;
`evaluate_real(dataset,predictions,annotations,split,seal,...)`. Unknown GT stays
NOT_EVALUABLE; synthetic and external metrics never aggregate. Use R2 pure-pixel
detect_rgb/detect_trained_rgb and matcher without faking R2 SYNTHETIC flags.
If resizing is needed for R2 4M-pixel bounds, freeze deterministic adapter settings
before inference, bind preprocessing and map boxes to original normalized coordinates.

Report in report.py/review_ui.html reads actual dataset/predictions/evaluation/
annotations. public_export requires every embedded image's redistribution permission
and attribution/derivative license; otherwise local controlled view or no-image index.
Missing reference => null/NOT_EVALUABLE, no guessed zero. Source domains stay visible.
Annotations UI exports fresh drafts/history only, never approved/reviewer authentication.

All team APIs may add keyword defaults; message root/other owners promptly when
types/signatures become concrete. New tests are test_r3_*.py; keep original271 tests.
Compact evidence: no duplicated AP traces, no bulk dataset JSON/images in GitHub.
