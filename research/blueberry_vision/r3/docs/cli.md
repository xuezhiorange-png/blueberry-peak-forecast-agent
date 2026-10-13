# R3 offline research commands

Run from the repository root with the independent pinned research environment:

```bash
python -m pip install -r research/blueberry_vision/requirements-r3.txt
python -m research.blueberry_vision.r3.cli --help
python -m research.blueberry_vision.r3.cli run-r3-acceptance --output /tmp/vision-r3-acceptance-001 --coco
```

`run-r3-acceptance` actually runs the inherited R1/R2 pytest suite and the R3
pytest files, then reads PNG bytes, binds a synthetic engineering dataset, audits
quality, finds re-encoded duplicates, rejects cross-split leakage, creates and
retains simulated two-annotator histories, adjudicates and seals candidates,
round-trips COCO annotations, freezes original R2 A/B artifacts, reloads the
original trained NumPy model, executes pixel inference, seals references, records
exposure events, evaluates independent painted geometry, generates HTML and
verifies file hashes. The fixtures contain two independently encoded copies of
one painted target and an explicitly annotated zero-target image. Both copies
remain in the same engineering test group. These are engineering goldens, not
real blueberry accuracy or independent human annotation agreement.

Every run requires a fresh output directory. The CLI will not replace prior
outputs. When pytest has already run in the invoking CI job, use `--skip-tests`
(alias `--skip-regression`); the receipt explicitly records
`NOT_RUN_EXPLICIT_PIPELINE_ONLY`, without claiming pytest ran again. `--coco`
requests the actual optional pinned `pycocotools` evaluator; ordinary research AP
retains its separate name. The acceptance operation neither downloads images,
trains an R3 model, connects to a database nor starts a service.

## Real image ingestion and immutable pixel inference

The following commands consume an authorized local data root, reviewed registry,
and independent source index. A source index lists relative image paths and
source IDs; source permissions come from the registry. No creation timestamp is
used as capture time. An unknown identity remains unresolved.

```bash
python -m research.blueberry_vision.r3.cli discover-sources --output /tmp/source-review.json
python -m research.blueberry_vision.r3.cli import-images --data-root /tmp/licensed-images --source-index /tmp/source-index.json --registry /tmp/source-review.json --output-dir /tmp/import-001
python -m research.blueberry_vision.r3.cli audit-images --manifest /tmp/import-001/dataset_manifest.json --data-root /tmp/licensed-images --output /tmp/quality-001.json
python -m research.blueberry_vision.r3.cli find-near-duplicates --manifest /tmp/import-001/dataset_manifest.json --data-root /tmp/licensed-images --threshold 6 --output /tmp/duplicates-001.json
python -m research.blueberry_vision.r3.cli freeze-baselines --output /tmp/freeze-001.json
python -m research.blueberry_vision.r3.cli run-real-inference --manifest /tmp/import-001/dataset_manifest.json --data-root /tmp/licensed-images --freeze /tmp/freeze-001.json --model A --ledger /tmp/exposure-A-001 --output /tmp/prediction-A-001.json
python -m research.blueberry_vision.r3.cli run-real-inference --manifest /tmp/import-001/dataset_manifest.json --data-root /tmp/licensed-images --freeze /tmp/freeze-001.json --model B --ledger /tmp/exposure-B-001 --output /tmp/prediction-B-001.json
```

`discover-sources` defaults to the retained reviewed catalog, without network
requests. `--online` explicitly refreshes official source and license metadata;
it does not implicitly download images. An explicit
`discover-sources --download-quality /tmp/quality-pilot-001 --output /tmp/review-with-download.json`
reproduces the bounded first-four sorted image selection from the official
CC BY 4.0 Quality dataset using its source module. It preserves original image
bytes and publisher annotation files, and creates separately versioned first-frame
PNG derivatives. Publisher candidate annotations remain pending quality review;
downloading them does not upgrade them to qualified human GT. No whole multi-GB
archive is downloaded. This optional network operation is separate from ordinary
offline acceptance and CI.

To reproduce the merged eight-photo pixel pilot, retain the independently
verified Commons acquisition directory, the Quality acquisition directory and
their reviewed source-registry supplement. Prepare an asset-only directory before
import; publisher object counts and candidate annotations do not enter its
pixel manifest:

```bash
python -m research.blueberry_vision.r3.cli discover-sources --download-commons /tmp/commons-pilot-001 --output /tmp/commons-acquisition-review.json
python -m research.blueberry_vision.r3.cli discover-sources --download-quality /tmp/quality-pilot-001 --output /tmp/quality-acquisition-review.json
python -m research.blueberry_vision.r3.cli prepare-public-pilot --commons-root /tmp/commons-pilot-001 --quality-root /tmp/quality-pilot-001 --registry research/blueberry_vision/evidence/r3/data_source_registry.json --supplement /tmp/verified-quality-source-supplement.json --output /tmp/merged-pilot-001
python -m research.blueberry_vision.r3.cli import-images --data-root /tmp/merged-pilot-001 --source-index /tmp/merged-pilot-001/source_index.json --registry /tmp/merged-pilot-001/source_registry.json --output-dir /tmp/merged-import-001
```

The preparation helper rechecks authorized source licenses and image SHA256,
copies safe bounded pixels exclusively into `commons/` and `quality/`, preserves
unknown dates and identities and retains original/derivative provenance. It
does not copy raw MPO files or reference labels into the asset index. Sources
unrelated to the selected assets are not silently admitted from the discovery
catalog. Reusing an existing output directory is rejected.

Inference has no annotation/GT argument. A new ledger first records the actual
configuration freeze. Inference writes its prediction file before appending the
prediction-fixed event. R2 algorithm thresholds and original model are retained;
the preregistered resize adapter is frozen. Both algorithms return visible target
counts from pixels, without interpreting those counts as kg.

## Candidate annotations, split and controlled scoring

For ordinary third-party COCO, supply category and image maps with integer IDs as
JSON string keys, plus an explicit version and retained source provenance. A
COCO image ID is not inferred from a filename. The provenance contract does not
verify license websites or authenticate humans; the source review must actually
support any asserted publisher annotation evidence. Example mapping:
`{"1":"CANDIDATE_VISIBLE_BLUEBERRY"}`. Controlled R3 COCO exports already carry
their source snapshots and do not require replacement evidence.

```bash
python -m research.blueberry_vision.r3.cli import-annotations --manifest /tmp/import-001/dataset_manifest.json --coco /tmp/authorized-coco.json --category-map /tmp/category-map.json --image-map /tmp/image-map.json --annotation-version publisher-v1 --provenance /tmp/annotation-evidence.json --output /tmp/annotations-001.json
python -m research.blueberry_vision.r3.cli review-annotations --action create --manifest /tmp/import-001/dataset_manifest.json --image-id sample-one --annotation-version local-draft-v1 --actor self-asserted-user --objects /tmp/candidate-objects.json --output /tmp/draft-v1.json
python -m research.blueberry_vision.r3.cli review-annotations --action transition --snapshot /tmp/draft-v1.json --state SUBMITTED --actor self-asserted-user --output /tmp/submitted-v1.json
python -m research.blueberry_vision.r3.cli review-annotations --action compare --snapshot /tmp/first-review.json --other /tmp/second-review.json --actor self-asserted-user --output /tmp/disagreement-001.json
python -m research.blueberry_vision.r3.cli review-annotations --action adjudicate --snapshot /tmp/first-review-pending.json --other /tmp/second-review-pending.json --objects /tmp/adjudicated-objects.json --annotation-version local-adjudication-v1 --actor self-asserted-third-user --output /tmp/adjudicated-v1.json
python -m research.blueberry_vision.r3.cli review-annotations --action transition --snapshot /tmp/adjudicated-v1.json --state SEALED --actor self-asserted-third-user --output /tmp/sealed-v1.json
python -m research.blueberry_vision.r3.cli review-annotations --action export-coco --snapshot /tmp/annotations-001.json --actor self-asserted-user --output /tmp/exported-coco-001.json
python -m research.blueberry_vision.r3.cli build-split --manifest /tmp/import-001/dataset_manifest.json --assignments /tmp/explicit-assignments.json --duplicates /tmp/duplicates-001.json --split-version pilot-v1 --output /tmp/split-001.json
python -m research.blueberry_vision.r3.cli seal-test --manifest /tmp/import-001/dataset_manifest.json --split /tmp/split-001.json --annotations /tmp/annotations-001.json --freeze /tmp/freeze-001.json --ledger /tmp/exposure-A-001 --output /tmp/seal-001.json
python -m research.blueberry_vision.r3.cli evaluate-real --manifest /tmp/import-001/dataset_manifest.json --predictions /tmp/prediction-A-001.json --annotations /tmp/annotations-001.json --split /tmp/split-001.json --test-seal /tmp/seal-001.json --freeze /tmp/freeze-001.json --ledger /tmp/exposure-A-001 --coco --output /tmp/metrics-A-001.json
```

Objects files have `{"objects":[...]}` and contain versioned candidate labels,
half-open `bbox_xyxy` and `TARGET`, `IGNORE` or `UNCERTAIN` disposition. Omitting
`--objects` preserves `UNANNOTATED` with count null; `{"objects":[]}` explicitly
declares zero targets. An unannotated draft cannot be submitted. Synthetic
annotation flows require explicit `--workflow-mode SIMULATED_ENGINEERING`.
Offline actor IDs always remain unauthenticated and do not confer business
approval. Adjudication requires two distinct pending annotators and a third
asserted adjudicator. Each output is a new file with inherited version history.

Assignments are an explicit JSON object such as `{"image-one":"TEST"}`;
unassigned images retain `UNASSIGNED`. Connected source/duplicate/session groups
cannot cross assigned splits. Qualified references, frozen configuration,
unchanged test scope, ordered exposure ledger and fixed predictions are required
for scoring. Missing GT or failed admission creates `NOT_EVALUABLE` with null
metrics and reason codes, not a fake zero. Public labels remain
`EXPOSED_PUBLIC_BENCHMARK`; the seal does not provide independent access control.

## Actual report and artifact verification

```bash
python -m research.blueberry_vision.r3.cli render-real-report --manifest /tmp/import-001/dataset_manifest.json --data-root /tmp/licensed-images --predictions /tmp/prediction-A-001.json /tmp/prediction-B-001.json --evaluations /tmp/metrics-A-001.json /tmp/metrics-B-001.json --annotations /tmp/annotations-001.json --output-dir /tmp/review-001
python -m research.blueberry_vision.r3.cli verify-artifacts --manifest /tmp/vision-r3-acceptance-001/artifact_manifest.json
python -m research.blueberry_vision.r3.cli verify-artifacts --manifest research/blueberry_vision/evidence/r3/artifact_manifest.json --root .
```

The report consumes the actual outputs, exposes each source domain and license,
and keeps unavailable reference counts null. The default report is a controlled
local artifact. `--public-export` embeds previews only when verified source
permissions allow redistribution; otherwise the public index contains no pixels
for that image. Source attribution and derivative notices remain visible.

Artifact indexes are `ENGINEERING_ARTIFACT_INDEX` file inventories. They contain
no blanket `SYNTHETIC` assertion; each indexed data contract retains its own
domain. Every declared file is bounded, rooted, SHA256- and size-verified;
traversal, symlinks including root ancestors, nonregular files, duplicate paths
and tampering are rejected. The index excludes itself. Administrative acceptance
receipt `acceptance.json` is written after successful verification and is outside
that run's preceding file snapshot; the final GitHub index can bind that receipt
in a new declared snapshot. No absolute host path or clock enters pixel/model
prediction hashes. Exposure event timestamps are separate audit metadata.

CLI exit codes: `0` means the command completed (including an explicitly
`NOT_EVALUABLE` evaluation); `1` means acceptance/integrity checks failed; `2`
means invalid input, rejected source/path/state, unavailable output or exception.
Every failure is retained rather than replaced by a claimed PASS.
