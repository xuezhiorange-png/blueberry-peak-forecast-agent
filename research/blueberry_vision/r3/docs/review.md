# R3 offline image review and annotation workbench

The renderer consumes the actual R3 asset manifest, frozen R2 prediction bundles,
compact R3 evaluation reports, and separate annotation snapshots. It opens licensed
images with `r3.ingestion.secure_load_asset`, verifies source SHA256 and normalized
sizes, and creates resized RGB/JPEG previews. It does not use image IDs, filenames,
reference boxes or counts to generate predictions. Inference is a separate operation.

```python
from pathlib import Path
from research.blueberry_vision.r3.report import render_report

render_report(dataset, Path("authorized-images"), [baseline_a, baseline_b],
              [evaluation_a, evaluation_b], annotation_bundle_or_none,
              Path("new-report-directory"), public_export=False)
```

Every output directory is new; existing reports and original images are never
replaced. `report.html` works offline without a production service, external scripts,
fonts or cloud APIs. `report.json` is compact and contains no image bytes or local
asset paths. `report.md` provides scalar results, coverage and attribution. Model,
config, dataset, prediction and evaluation hashes remain visible. The report verifies
seals and image binding, then recomputes visible-count errors, IoU matching, research
AP50, scalar metrics and density/occlusion/lighting strata from the supplied references.
It rejects stale or resealed false scores, unqualified real-reference claims, changed
protocols and hidden substitution of synthetic results for external results.

The header distinguishes `SYNTHETIC_ENGINEERING`, `PUBLIC_EXTERNAL_BENCHMARK`, and
`AUTHORIZED_ORCHARD_PILOT`. Each report has one source domain; domains are never pooled
into an accuracy average. Source selection filters image sources within that domain.
Each image shows its creator, source and license links, permitted distribution,
preview changes, annotation state, unresolved Base identity and unknown capture time.
Public images do not become company orchard observations.

## Distribution and repository size

`public_export=True` only embeds images whose source explicitly has
`redistribution=true`; all other records become metadata-only, with
`REDISTRIBUTION_NOT_AUTHORIZED`. A local controlled report may embed research-authorized
images without redistribution permission, but must remain in authorized local storage
and must not be committed or published. The mode is prominently marked in the page and
Markdown. A local image path is never converted into a public Web URL. No browser fetch,
upload, telemetry or automatic source-site request occurs.

The preview attribution identifies the source creator and license, with source and
license links. It declares EXIF normalization, RGB conversion, resizing and JPEG
encoding. CC BY-SA image derivatives retain the original BY-SA license; the page's
research code is a separate artifact. Source license conditions remain visible.

Defaults limit display to 50 images, previews to a 900-pixel maximum edge, embedded
image data to 10 MB, and the entire HTML to 12 MB. The compact JSON omits AP curves and
large intermediate logs. Coverage explicitly reports total, displayed, embedded and
not-displayed images. Aggregate metrics and count-error histograms use the complete
supplied evaluation scope, including excluded and failed images; display truncation
never changes a score. Full source/annotation/prediction indexes remain the separate
versioned artifacts rather than repeated copies in each report.

## Read-only evaluation

The workbench supports model switching, prediction/annotation visibility toggles,
FP/FN emphasis, and filters for missing GT, inference failure, verified empty reference,
high count error, density, occlusion and lighting. Missing scene metadata stays
`UNKNOWN`. Qualified reference labels alone produce TP/FP/FN and count errors. For
unannotated or inadequately reviewed real images, the reference count, count error,
Precision/Recall and MAE/Bias display `NOT_EVALUABLE`; actual prediction counts remain
visible. A zero prediction is distinguished from missing GT and inference failure.
The page draws count-error distributions, Precision/Recall, MAE/Bias, density/occlusion
strata and evaluation coverage using the actual compact report data. Unknown metrics
are neither guessed nor drawn as zero bars. Missing predictions from the declared sealed
scope remain explicit excluded rows with null counts, separate from missing GT and
decode/inference failures. Coverage reports and charts retain `missing_prediction_count`. COCO mAP is only displayed when the recorded
formal COCO adapter actually ran; research AP50 is named separately.

## Candidate draft editing

Choose **New empty draft** or **Copy displayed annotation**. Draw a box with the mouse;
select inside a box to move it, drag one of its corners to resize, and delete a selected
box. Use the candidate class and `TARGET`, `IGNORE`, or `UNCERTAIN` disposition. Only
`CANDIDATE_VISIBLE_BLUEBERRY` can be a target; unresolved clusters and non-target
interference cannot silently become a blueberry reference. Mark candidate coverage as
`COMPLETE` only when the operator has completed the image. `EMPTY_VERIFIED` is an
explicit candidate zero-target claim, permitted only when no target box remains.
An unannotated draft retains `objects=null` and all counts null; unfinished geometry
is stored separately in the bundle’s `pending_editor_objects`, outside the strict snapshot.

**Export new draft + history** downloads a fresh, hash-bound R3 annotation bundle.
`snapshots` contains the new `DRAFT`; `archived_versions` preserves previous exports.
Every snapshot has a new version and hash, original image/source identity, parent
snapshot hashes, label definition, candidate approval status, and a self-asserted
operation log. Source GT is never changed. Browser geometry is rounded to 0.001 pixels
to preserve canonical hash parity with Python. The bundle can be read by the R3 review
CLI and the snapshot validated by `annotations.validate_snapshot`. Use **Import candidate
draft bundle** to reopen a hash-bound candidate bundle for a new editor version; source
image identity and all archived snapshot hashes must agree. Importing never replaces GT.

Entering an operator ID does not authenticate that operator. Draft exports always
have `identity_authenticated=false`, `business_approved=false`, and candidate label
status. Synthetic editing uses `SIMULATED_ENGINEERING`; this never creates a real
human reference. Drawing/edit operations do not transition the review state. Two
independent versions, review transitions, adjudication and sealing run through the
separate R3 annotation contract/CLI, which retains immutable history and checks its
state machine. The HTML does not invent a second reviewer, human evidence or approval.

**Export candidate COCO** preserves candidate status, source asset hash, annotation
version, category mapping, image dimensions, bbox geometry and ignore dispositions.
It is a candidate interchange, not a publisher GT claim. **Export analysis JSON**
exports compact results without preview image bytes. No export overwrites old files.
Cryptographic draft export requires browser WebCrypto; it blocks explicitly if secure
hashing is unavailable instead of emitting a fake identifier.

## Validation and remaining gates

Owned tests execute the actual geometry and WebCrypto helpers in Node, verify canonical
hashes against Python, and check missing GT, real/synthetic identity, attribution,
redistribution rejection, symlink roots/ancestors, annotation binding, untrusted HTML
metadata, stale metrics, protocol freeze, and bounded output behavior. Browser
acceptance operates on the rendered HTML and downloads a real candidate bundle for
Python schema/hash validation. This cloud's installed Chromium restricts `file://`
navigation; acceptance can intercept one reserved HTTPS URL and fulfill it entirely
from the local HTML without a network fetch or deployment. Ordinary offline use can
open the HTML directly where browser policy permits local files.

No visual count-to-kg conversion, mature-stage business classification, orchard model
approval or production service is part of the review workbench. Real benchmark accuracy
requires licensed pixels, qualified independent human references, source/asset agreement,
a leakage-free declared evaluation scope, frozen model/configuration and a recorded
seal/exposure process. An image's ability to decode is not a label-quality approval.

Unreviewed source geometry in `annotation_bundle.draft_geometry[image_id]` is checked
against the hash-bound bundle, snapshot image/source identity and actual image bounds.
The page displays it as **Unreviewed candidates**, separately from GT. Copying candidates
starts a new unannotated draft for manual review; it never fills reference counts or
accuracy metrics. Actual EXIF orientation, original dimensions and normalized coordinate
frame are checked against decoded pixels, including resealed-but-inconsistent metadata.
