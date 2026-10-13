# R3 acceptance record

TASK_ID=BLUEBERRY_VISION_R3_REAL_IMAGE_PILOT_AND_VALIDATION

Engineering: PASS. Fresh271 inherited R1/R2 tests and363 R3 tests passed; complete suite634 passed,0 skipped. Ruff46files and strict mypy46files passed. Default run-r3-acceptance independently reran the two suites and completed13 actual engineering checks, including pixel inference, original model reload, independent goldens, COCO roundtrip, split rejection, seal/ledger, actual HTML and file hashes. Acceptance fixtures are SYNTHETIC_ENGINEERING; their scores are not real accuracy.

Public pilot: PARTIAL. Four licensed Commons JPEGs plus four licensed Quality dataset PNG derivatives admitted. Both frozen R2 models ran successfully on all eight images (16 model/image runs). No real training or threshold selection. Model/config/adapter/source hashes were frozen before scoring. A corrected source-quality admission guard required a new immutable run; all per-image pixel outputs remained exactly equal to the prior run.

References: NOT_EVALUABLE. Source review audited27 XML files and675 polygons, all semi-auto. Selected100 boxes remain unreviewed candidates; no qualified GT, no real Precision/Recall/AP/MAE/Bias/COCO result. Public labels are EXPOSED_PUBLIC_BENCHMARK. Actual test admission/seal returns explicit GT_MISSING / GT_QUALITY_INSUFFICIENT / REFERENCE_HUMAN_EVIDENCE_NOT_VERIFIED.

Visual review: PASS. One licensed public HTML reads actual8-image predictions, source permissions and candidate drafts. Chromium verified model counts1161→66, source switching, pending25-box copy/edit/export, Python snapshot/hash validation, NOT_EVALUABLE metrics, no fake FP rows and zero page errors. No service deployment or external vision API.

Boundaries: all233 inherited research files remained byte-identical; original232-file R2 artifact seal remained valid. Production API/MCP, Harvest State, frozen models/evidence, prediction records and main were not modified. No company/private orchard/DB/current-season actual accessed. No Ready/Merge/Tag/Release/Deploy authorization.

Persistence: M0–M6 ordinary commits were pushed and remote HEAD verified individually. M7 is the current checkpoint, whose own SHA is intentionally not embedded. Final remote HEAD, stacked Draft PR and exact-head CI are reported in the final receipt/PR. GitHub is the durable source. The final versioned artifact index binds code, contracts, compact evidence, progress, licensed images and HTML; it excludes itself.
