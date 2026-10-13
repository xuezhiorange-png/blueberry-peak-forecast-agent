# R3 candidate visible-fruit annotation and offline review

`candidate-visible-blueberry/3.0.0` defines a research candidate task: detection
and counting of individually distinguishable visible blueberries in one image.
It does not define maturity, the number of hidden fruit, a whole-plant estimate,
or kilograms. Dataset owners must confirm the candidate definition before an
orchard trial. R1 and R2 labels and schemas remain unchanged.

| Case | Candidate annotation rule |
| --- | --- |
| One distinguishable visible blueberry | One `TARGET` box around its visible extent, label `CANDIDATE_VISIBLE_BLUEBERRY`. |
| Two touching but individually distinguishable berries | Two separate `TARGET` boxes; do not convert a cluster into one fruit. |
| Partial occlusion | A `TARGET` only when the individual fruit is identifiable; box visible extent and record optional occlusion notes. |
| Uncertain target identity or location | `UNCERTAIN`; excluded from reference visible count and reported separately. |
| Cluster whose individual fruit cannot be resolved | `IGNORE`, label `UNRESOLVED_FRUIT_CLUSTER`; no invented individual count. |
| Partly outside image | Target only if individually identifiable; clip the box to the actual normalized image boundary. |
| Non-blueberry visual interference | `IGNORE`, label `NON_TARGET_DISTRACTOR`; never a positive target. |
| Truly inspected zero-target image | Explicit `objects=[]`, `gt_status=COMPLETE`, `visible_count=0`. |
| Not annotated | `objects=null`, `gt_status=UNANNOTATED`, all count fields `null`. |

`TARGET` alone contributes to `visible_count`; ignore and uncertain counts have
separate fields. Counts use `visible_fruit_per_image`. Bounding boxes are
continuous half-open `[x1,y1,x2,y2]` in normalized image coordinates, with
strictly positive area and no out-of-bounds coordinates. No physiological
maturity classes are inferred from color. The schema is stored in
`../annotation_snapshot.schema.json`; code additionally checks cross-field
counts, hash seals, image provenance and legal review history.

Every snapshot binds `image_id`, source ID, original byte SHA256, normalized
width/height, dataset purpose, synthetic flag, annotation version, label version,
provenance, count policy, history and `snapshot_hash`. The asset manifest contains
no GT. `annotation_bundle(dataset,snapshots)` verifies that each snapshot belongs
to the dataset and creates an independent `annotations_hash`. Reusing one image
in multiple *annotation versions* is allowed; a bundle contains one chosen
version per image. Former versions remain separate immutable records.

The workbench APIs in `research.blueberry_vision.r3.annotations` are:

- `create_draft(image_record, annotation_version=..., annotator_id=..., objects=...)`.
- `import_annotations(dataset,coco, annotation_version=..., category_mapping=..., image_mapping=..., provenance=...)`.
- `export_coco(bundle_or_snapshot_list)`.
- `compare_annotations(a,b,iou_threshold=0.5)`.
- `transition_review(snapshot,target_state,actor_id=...,at=...)`.
- `adjudicate_annotations(a,b,objects,adjudicator_id=...,annotation_version=...)`.
- `save_snapshot(output_dir,snapshot)`, which writes a new content-addressed file
  using exclusive creation and never replaces a previous record.

A plain external COCO import needs an explicit category mapping, numeric image-ID
mapping, annotation version and source provenance. Strict positive integer IDs
exclude booleans and floating IDs. Box `xywh` converts to `xyxy`; geometry,
classes, image dimensions and IDs are checked. COCO crowd boxes become `IGNORE`,
without asserting an individual count. Masks/RLE are unsupported and rejected.
Controlled COCO exports retain the entire source snapshot and per-object
metadata. Re-import must preserve geometry, object count, dispositions, source,
version and original hash exactly. Edited geometry requires a *fresh* draft.
An imported model prediction or AI annotation cannot become a reference by
renaming its fields or running this converter. Candidate labels remain candidate.

The legal state sequence is:

`DRAFT → SUBMITTED → REVIEW_PENDING → ADJUDICATED → SEALED`.

Only `adjudicate_annotations` creates `ADJUDICATED`, using two `REVIEW_PENDING`
source snapshots with distinct asserted annotator IDs, plus a third asserted
adjudicator ID and a new annotation version. Each operation appends an event,
links the previous snapshot hash and returns a new snapshot. Adjudication retains
both source hashes and their origin claims. The second source snapshot remains
in the immutable history store. Known operation timestamps must be timezone-aware
and cannot move backwards; missing operation time remains `UNKNOWN`. Capture
time is never derived from an annotation event or file creation time.

All locally entered actor IDs are self-asserted: `identity_authenticated=false`.
All outputs have `business_approved=false`, including sealed snapshots. A seal
is an integrity and workflow check, not authenticated identity or production
access control. `SIMULATED_ENGINEERING` is required for synthetic images and
is explicitly rejected by real-reference qualification even after sealing.
A simulated workflow can prove state-machine execution but cannot prove actual
human agreement.

`compare_annotations` uses the existing R2 same-class, IoU-threshold, one-to-one
matcher with equal scores and stable object order. It reports signed count
change (B−A), matched targets, `2×matches/(targets_A+targets_B)`, mean matched IoU,
unmatched IDs and uncertain ratio. Duplicate boxes cannot share one reference.
No targets produces a null matched ratio and IoU. Missing annotation produces
`NOT_EVALUABLE`, without converting null to zero. Adjudication ratio is the
number of unmatched source targets divided by total source targets, rather than
an assessment of the arbitrator's accuracy. Matching metrics are computable from
asserted snapshots, but only genuinely independent human versions can support a
claim about human consistency; the API reports independence as unverified.

`reference_eligibility` requires complete labels and rejects synthetic or simulated
reviews. Documented publisher reference requires explicit `HUMAN` origin,
`DOCUMENTED_PUBLISHER_ANNOTATION`, `evidence_status=VERIFIED`, retained evidence
references, original annotation version and original annotation SHA256. Publisher
reference qualification is separate from local workflow status: an original
published reference can retain a local conversion `DRAFT` status without inventing
a local dual review. Public references are `EXPOSED_PUBLIC_BENCHMARK`.

An orchard human reference additionally needs a sealed independent adjudication,
HUMAN origins for both source versions and an externally verified human evidence
attestation. The caller must actually verify and retain these records before
asserting their evidence status. The module does not verify websites or authenticate
people. Merely submitting, adjudicating or sealing self-asserted drafts does not
qualify a real reference. Source license admission, split isolation and test
configuration freezing are additional gates applied by the R3 split/evaluation
modules. No business-approved review state is synthesized by any of these APIs.

Known interchange metadata constrains qualification. A plain COCO source marked
`info.candidate=true`, `annotation_status=DRAFT/SUBMITTED/REVIEW_PENDING`, or a
semi-automatic annotation method without verified source human review cannot be
upgraded by supplying a new publisher/HUMAN/VERIFIED provenance argument. This
raises `ANNOTATION_PROVENANCE_AUTHORITY_UPGRADE`. Known model/AI/automatic prediction
origins raise `PREDICTION_IS_NOT_GT`. Source restrictions are retained as
`provenance.imported_source_quality` and rechecked by reference qualification.
Retained embedded draft snapshots continue to constrain import if the controlled
adapter wrapper is removed. This is preservation of known source claims; the
module cannot reconstruct metadata deliberately removed from an untrusted file.

Plain candidate COCO keeps explicit `TARGET/IGNORE/UNCERTAIN` dispositions. A crowd
box cannot claim `TARGET`. Candidate COCO must explicitly state
`info.gt_status=COMPLETE` to claim completed candidate coverage; otherwise its
snapshot remains `UNANNOTATED`, and editable geometry is retained in the bundle's
`draft_geometry` outside the reference objects. This prevents pending editor boxes
or an empty unfinished editor from silently becoming complete GT. Candidate source
asset SHA256, purpose and synthetic declarations are checked against the dataset.

Plain external COCO coordinates also require a known pixel frame. New imports
record actual `exif_orientation`, original dimensions and
`image_coordinate_frame=EXIF_NORMALIZED_RGB_HALF_OPEN_XYXY`. A nontrivial EXIF
orientation, or a legacy unknown orientation, blocks plain COCO import with
`ANNOTATION_COORDINATE_FRAME_UNVERIFIED` unless retained source evidence explicitly
confirms normalized annotation coordinates. The evidence fields are
`coordinate_frame=EXIF_NORMALIZED_RGB_HALF_OPEN_XYXY`,
`coordinate_frame_status=VERIFIED`, and nonempty `coordinate_frame_evidence_ref`
(or `coordinate_frame_evidence_refs`). The importer also accepts the explicit
aliases `annotation_coordinate_frame` and `coordinate_frame_evidence_status`.
This frame evidence is distinct from annotation human quality and can accompany
unverified candidate labels. Boxes are not guessed, mirrored or rotated by the
converter. Correct dimensions alone cannot prove correct mirrored coordinates.

The same source restriction applies to the Quality COCO source aliases
`annotation_quality_status=DRAFT`, `label_approval=CANDIDATE_ONLY`,
`annotation_origin=UNVERIFIED`, and `evidence_status=PENDING_QUALITY_REVIEW`.
Known UNKNOWN/UNVERIFIED/UNREVIEWED origins or evidence, and pending evidence,
are retained as candidate restrictions; an import argument cannot override them.
Their boxes stay in `draft_geometry` unless the source explicitly declares
completed candidate coverage. Neither completed candidate coverage nor an
explicit hash turns these pending-quality labels into eligible real GT.
