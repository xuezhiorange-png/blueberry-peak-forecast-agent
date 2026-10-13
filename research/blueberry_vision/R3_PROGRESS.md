# R3 recovery checkpoint

TASK_ID=BLUEBERRY_VISION_R3_REAL_IMAGE_PILOT_AND_VALIDATION
BRANCH=research/blueberry-vision-r3-real-image-pilot
SOURCE_R2_HEAD=eacc86d16c635136ac24461af2e8657dd5e7c23d
R3_START_HEAD=eacc86d16c635136ac24461af2e8657dd5e7c23d
BASE_MAIN_SHA=c35524174865785164fe4529f35067037ccddc2a
PARENT_PR=719 (unchanged OPEN_DRAFT)

| Stage | Accepted state | Commit |
| --- | --- | --- |
| M0 | COMPLETE_PUSHED | `2772f6a68a3a3095c3e2883a70ae6de044ff989b` |
| M1 | COMPLETE_PUSHED | `a15c56d6634e69db3715b86e2b5e8f63bb28aee1` |
| M2 | COMPLETE_PUSHED | `35b2cd36d72297efbe83fc3aa4bc54019d531f3a` |
| M3 | COMPLETE_PUSHED | `f5ac493886f6c38c8db62cdf94f35bbe5ab06bdf` |
| M4 | COMPLETE_PUSHED | `5d83ca8a0b89161578c0885d63ac87ded6208aff` |
| M5 | COMPLETE_IN_CURRENT_CHECKPOINT | current checkpoint subject: `feat(vision-r3): adapt frozen baselines and real benchmark evaluation` |
| M6 | PENDING | pending own accepted checkpoint |
| M7 | PENDING | pending own accepted checkpoint |

Current checkpoint parent `5d83ca8a0b89161578c0885d63ac87ded6208aff`. Own SHA intentionally not self-embedded;
next checkpoint/remote log/final receipt supplies it. Completed prior stages were
ordinary-pushed and remote HEAD verified; local parallel files are not milestones.
Actual commands/exit/stdout/facts: evidence/r3/m5_checkpoint.json.
R2 original271 fresh tests passed in M0, original232 artifact seal verified; all
inherited research bytes checked unchanged before every checkpoint.

Data status: 8 licensed public real images; 100 semi-auto candidate draft boxes; 0 qualified GT.16/16 actual A/B inference; real accuracy null/NOT_EVALUABLE..
Known blockers: All675 publisher polygons semi-auto without documented human confirmation. No private orchard authority or trustworthy real per-fruit GT..
No company/private orchard/DB/current-season actual access, no production forecast/
Harvest State/frozen model changes. Source purpose stays PUBLIC_EXTERNAL_BENCHMARK/
AUTHORIZED_ORCHARD_PILOT/SYNTHETIC_ENGINEERING, unknown date/identity stays unknown.
No automatic reviewed business labels, no count→kg, no real orchard approval.

Next: M6 public-license-aware actual 8-image HTML, pending candidate editing and browser verification; M7 CLI/test/hash CI acceptance..
Stage artifact paths: research/blueberry_vision/r3/contracts.py, research/blueberry_vision/r3/ingestion.py, research/blueberry_vision/r3/dedup.py, research/blueberry_vision/r3/sources.py, research/blueberry_vision/r3/annotations.py, research/blueberry_vision/r3/splits.py, research/blueberry_vision/r3/evaluation.py, research/blueberry_vision/r3/public_pilot.py, research/blueberry_vision/tests/test_r3_sources.py, research/blueberry_vision/tests/test_r3_ingestion.py, research/blueberry_vision/tests/test_r3_dedup.py, research/blueberry_vision/tests/test_r3_annotations.py, research/blueberry_vision/tests/test_r3_evaluation.py, research/blueberry_vision/tests/test_r3_public_pilot.py, research/blueberry_vision/newtests/test_r3_splits.py, research/blueberry_vision/evidence/r3/pilot_dataset_manifest.json, research/blueberry_vision/evidence/r3/model_inference.json, research/blueberry_vision/evidence/r3/source_registry_supplement.json, research/blueberry_vision/evidence/r3/exposure_ledgers.json, research/blueberry_vision/evidence/r3/pilot_duplicate_review.json, research/blueberry_vision/evidence/r3/publisher_annotation_provenance_audit.json, research/blueberry_vision/evidence/r3/pilot_image_quality_report.json, research/blueberry_vision/evidence/r3/publisher_candidate_annotations.json, research/blueberry_vision/evidence/r3/public_quality_source_index.json, research/blueberry_vision/evidence/r3/real_benchmark_metrics.json, research/blueberry_vision/evidence/r3/source_registry_supplement_v2.json, research/blueberry_vision/evidence/r3/pilot_source_index.json, research/blueberry_vision/evidence/r3/evaluation_coverage.json, research/blueberry_vision/evidence/r3/pilot_test_seal.json, research/blueberry_vision/evidence/r3/pilot_split_manifest.json, research/blueberry_vision/evidence/r3/dependency_review.json, research/blueberry_vision/evidence/r3/config_freeze.json, research/blueberry_vision/r3/schema.json, research/blueberry_vision/r3/docs/annotation_rules.md, research/blueberry_vision/r3/docs/test_seal.md, research/blueberry_vision/r3/docs/evaluation.md, research/blueberry_vision/docs/r3_ingestion.md, research/blueberry_vision/requirements-r3.txt, research/blueberry_vision/evidence/r3/pycocotools_license.txt, docs/research/blueberry-vision-real-image-source-review-r3.md, research/blueberry_vision/evidence/r3/.gitattributes.
R3 keeps compact indexes/metrics/evidence. M0 audits inherited42.67MB research tree;
never delete/rewrite R2 history or add duplicated full AP curves/bulk private images.
GitHub is durable; external data uses official source/license/hash indexes and
bounded reproducible downloads. No credentials/signed URLs stored publicly.

Restore: fetch --prune, audit real R3 HEAD/worktrees and this file, continue accepted
commits rather than reset/rebuild. Install independent requirements-r3.txt when
available (includes fixed R2 requirements), Python3.12.14 CPU. R3 CLI lives in
research.blueberry_vision.r3.cli; no R1/R2 schema/gate relaxation. Final stacked
Draft PR base R2; leave PR719/main/Ready/Merge/Tag/Release/Deploy unchanged.
