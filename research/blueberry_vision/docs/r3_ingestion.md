# R3 external image ingestion and candidate duplicate review

`r3/contracts.py` and `r3/schema.json` define the independent
`blueberry-vision-external-dataset/3.0.0` asset contract. R1/R2 contracts stay
unchanged. The manifest contains no reference objects or model answers; annotation
snapshots and COCO image-ID indexing are separate. `PUBLIC_EXTERNAL_BENCHMARK`,
`AUTHORIZED_ORCHARD_PILOT` and `SYNTHETIC_ENGINEERING` cannot mix in one dataset.

Imports bind the canonical source registry snapshot to each normalized image.
Public sources require `LICENSE_VERIFIED` plus `research_use=true`; orchard sources
require `AUTHORITY_VERIFIED` and `authorization_evidence_ref`; generated regression
fixtures require `SYNTHETIC_AUTHORITY`. Model-training, commercial-use and
redistribution permissions remain separate original claims. Imported license
claims that disagree with the source snapshot fail. These checks verify the
recorded permission contract, not authorship, authenticated legal authority or a
commercial production approval. The source review evidence provides the external
license verification basis.

`import_images(data_root, source_index, registry, output_dir, coco=None)` reads
actual PNG/JPEG files through R2's bounded loader. It verifies SHA256, EXIF-oriented
dimensions, normalized RGB identity and preprocessing hash. Missing input hashes
in a locally authorized folder index are computed, never invented. An explicit
folder `source_id` is required. The dataset is immutable and refuses a nonempty
output directory. One failed image rejects the import; a later quality audit
retains a failed per-image record if bytes have changed. Maximum pilot bounds are
100 images, 500 MB cumulative original bytes, 20 MB/file, 25 MP/image, and 8192
pixels per side. A requested policy can reduce these limits.

The wrapper rejects symlinks in the root and all ancestors, parent traversal,
symlink assets, nonregular files, unsupported formats, corruption and decompression
bombs. Data roots must be controlled by the researcher during execution; the
root-ancestor check and R2's per-component `O_NOFOLLOW` reads are not an
authenticated multi-user storage service. Files remain root-relative local
references; originals are never changed or uploaded.

Capture time remains `null`/`UNKNOWN` when absent or lacking a verified timezone.
File mtime is never a capture date. Source-provided unverified date text is
preserved separately. An explicit timestamp requires timezone and a source or
authorized capture status. Public photographs cannot acquire company canonical
Base IDs. Unknown identity, variety, session, sampling unit, video and grouping
values stay unresolved; an import batch is not asserted to be a capture batch.

`audit_images(dataset, data_root)` reports resolution, aspect ratio, brightness,
contrast, saturation and Laplacian-variance blur candidates. Float computations
use a bounded 512×512 thumbnail and report its dimensions. Low resolution, extreme
brightness and low detail are review prompts. They never establish GT quality,
labelability or business maturity. Unavailable reference labels remain missing;
the label count is `null`, not zero. Coverage describes annotation references,
not accepted manual label quality.

`find_near_duplicates(dataset, data_root, threshold=6)` verifies every byte binding
and computes a 64-bit horizontal grayscale dHash using fixed Pillow LANCZOS
resampling to 9×8. It compares full views and center 75% crops. SHA256 and equal
normalized pixels are confirmed equality evidence; perceptual distance at or below
the threshold creates a `PENDING` relation. Arbitrary crops, rotations or
similar-looking fruit can cause false negatives or positives. It is a candidate
mechanism, not a solved image identity classifier or proof of the same fruit.

Declared sessions, sampling units, videos, source batches, parent/derivative and
multiview groups create separate association edges. Unknowns never form a shared
group. Split validation must consume all unresolved candidate relations and their
transitive connected groups. `review_duplicate` creates a new hash-linked review
snapshot with `CONFIRMED` or `REJECTED`, reason, time and an explicitly
unauthenticated reviewer ID. It preserves the original report. Equal bytes or
pixels cannot be manually rejected to enable leakage. Automated statuses are not
business label approval.
