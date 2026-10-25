# R2 known limitations and remaining gates

SYNTHETIC DEMONSTRATION — NOT REAL BLUEBERRY ACCURACY

- All 56 images and all references are generated; synthetic test/OOD are engineering
  checks. Shared rendering primitives and scene families do not demonstrate real
  field generalization. No real/private orchard images or current-season actual were read.
- Connected components merge touching/overlapping fruit. A has TP440/FP18/FN125 and
  11 error images; B has TP445/FP19/FN120 and 12 error images on the same 28 test/OOD
  images. All errors and all original predictions are retained. Dense/high-occlusion
  errors remain material. Averages do not prove statistical or business superiority.
- The lightweight classifier fits synthetic pixel labels on CPU. Region scores are
  uncalibrated research scores, and no deployed or approved blueberry model exists.
- AP50 is the implemented all-points research bounding-box AP, not COCO mAP50:95.
  No detection cap is applied; the 120-visible-object pressure cases are retained.
- Exact byte and normalized RGB duplicates and declared session/template/near-duplicate
  groups are rejected across splits. Automated perceptual near-duplicate discovery
  is not implemented. Real adjacent frames require reviewed grouping before admission.
- R2 is a separate synthetic adapter contract major version2.0.0. It does not upgrade
  R1 synthetic fixtures into real observations or approve candidate class/maturity labels.
- Missing references, failed inference and empty images have distinct evaluator semantics.
  Observations and weights retain provenance/version/hash; visible counts never convert to kg.
- The review page exports candidate drafts only. It provides no verified reviewer identity,
  multi-user review/audit service, automatic approval, segmentation/RLE or production storage.
- Browser file:// was blocked by this cloud Chromium administrator policy. The same final
  standalone HTML was tested through a fully intercepted in-memory localhost response,
  without a running web service or external network request. Browser evidence is recorded.
- PNG encoding/bytes depend on pinned Pillow/NumPy versions. Canonical models/predictions
  exclude timestamps/hostnames/absolute paths; tests independently verify repeatability.
- Optional YOLO/deep learning, pretrained weights, public dataset downloads, business data
  ingestion, actual orchard training, visual-weight calibration and deployment are not done.
- Research dependencies are isolated; production lock/API/MCP/Dashboard/Harvest State and
  frozen V0.15–V0.18 evidence remain unchanged. Existing repository CI is separate from
  research CI; only actually observed exact-head statuses may be claimed.

Before a real-image task, obtain explicit dataset rights and collection authorization,
canonical identities/session/frame grouping, candidate target and visibility/ignore rules,
reviewed labels and an independent held-out field set spanning bases/dates/cultivars/devices,
illumination and occlusion. Register frozen evaluation before model selection. Any kg/yield
experiment also needs separately authorized independent weighing, sampling coverage and
point-in-time calibration; image counts alone are insufficient.

GitHub Actions permission-settings inspection returned HTTP403 (integration lacks
that administrative read). Workflow execution/listing status is checked separately;
this administrative response alone is not evidence that CI cannot run.
