# R3 split graph and research test seal

The executable implementation is `r3/splits.py`. It is an independent external
benchmark contract at version `3.0.0`; it does not relax the R1 real-observation
gate or mutate the R2 synthetic dataset/model artifacts. Every artifact uses R2's
canonical SHA256 JSON convention and exclusive new-file output.

`build_split(dataset, assignments, duplicate_report=None)` accepts explicit
`TRAIN`, `VALIDATION`, `TEST`, `OUT_OF_DOMAIN`, and `UNASSIGNED` assignments. Missing
assignments stay `UNASSIGNED`. Image/normalized-RGB SHA equality, parent derivatives,
known capture sessions, sampling units, videos, source collection batches and
known-fruit multi-view groups produce graph edges. All frames with the same known
video ID are conservatively grouped; a temporal window is unnecessary for this
small research pilot. Import-operation batches do not establish a capture group.
Unknown/null association values never connect all unknown images together.

Pending perceptual duplicate candidates are also graph edges. The graph is closed
transitively, so an intermediate unassigned image cannot bridge `TRAIN` and `TEST`.
No connected component may occupy two assigned splits. Human rejection of a
perceptual candidate requires an asserted reviewer, review time, and reason;
this does not authenticate that person. Rejecting a candidate cannot remove an
independently established byte/RGB duplicate edge. The saved manifest contains
all association edges, connected groups, asset hashes, scope and split hash.
Admission rechecks declared associations rather than trusting edited group IDs.

Base/date holdout reports distinguish `VERIFIED_DECLARED_METADATA` and
`UNVERIFIED`. The first means complete declared identities/dates with no overlap
between train/validation and test/OOD; it does not certify source truth or field
generalization. Unknown capture dates remain unknown. Import time and filesystem
mtime are never used as capture time. Missing dates, unresolved identities, empty
comparison scope or overlap produce explicit reason codes. This pilot's public
photos have unresolved company identities and unknown capture dates, so those
holdouts are unverified.

`check_admission(dataset, split, annotations, freeze=..., test_seal=...,
predictions=..., ledger=...)` returns an admission artifact and per-image reasons.
Any failed scope gate returns `NOT_EVALUABLE`; failures are not silently discarded
to improve a score. Required checks include source-use authority/license,
dataset/split identity, sealed configuration and model/training/protocol hashes,
present versioned reference geometry, label definition consistency, genuine
reference provenance, source-asset binding, explicit nonnegative visible counts,
and annotated zero-target semantics. Prediction/model provenance cannot be GT.
Annotation qualification is delegated to the annotation module, preserving its
documented publisher/human evidence rules. Offline self-asserted or simulated
review is never upgraded into an authorized real-business reference.

If training belongs to the current dataset, `training_dataset_manifest_hash`
requires nonempty `training_image_ids`, all assigned `TRAIN`; validation is not a
fitting scope. Any declared `training_image_ids` or `training_asset_hashes`
overlapping test/OOD is rejected. The reused R2 model binds its original synthetic
training dataset hash instead of pretending that the external photos were its
training data. Declared provenance is checked; unreported historical exposure
cannot be proved absent by this offline system.

`seal_test(dataset, split, annotations, freeze, ...)` binds the dataset and split
hashes, test/OOD asset SHA256 values, annotation/label versions and hashes,
train/validation scope, algorithm configuration, model, training data and protocol.
Missing or unqualified GT produces a versioned `NOT_EVALUABLE` record instead of
a fake valid test seal. After a successful seal, changes to its asset/GT/split/
configuration scope are rejected with `SEALED_TEST_CHANGED`.

Public references are always `EXPOSED_PUBLIC_BENCHMARK`, including publisher GT
whose original labels are public. This is not a previously unseen blind test.
Synthetic review is marked `SIMULATED_ENGINEERING` and remains an engineering
exercise, even if its workflow reaches `SEALED`. No seal grants company label
approval, real orchard accuracy approval, or a fruit-count-to-kg calibration.

For scoring, use a separate immutable exposure ledger directory:

```python
append_exposure_event(ledger_dir, "CONFIG_FROZEN", {"freeze_hash": freeze_hash})
append_exposure_event(ledger_dir, "PREDICTIONS_FIXED", {
    "freeze_hash": freeze_hash, "prediction_hash": prediction_hash,
})
# This event precedes the evaluator's reference scoring read.
append_exposure_event(ledger_dir, "GT_SCORE_READ", {
    "freeze_hash": freeze_hash, "prediction_hash": prediction_hash,
    "annotations_hash": annotations_hash,
})
```

Each event is a distinct numbered JSON file written exclusively, with a sequence,
prior-event hash, canonical event hash, actual UTC operation record, unauthenticated
operator ID and optional actual artifact-file SHA256. Missing/changed files,
invalid sequence/hash chain and scoring before fixed predictions are rejected.
Admission requires the score-read event to match the current frozen configuration,
predictions and GT bundle. Do not backfill these events after scoring. The
timestamps are audit records; they do not enter algorithm/model prediction hashes.

The ledger and seal provide **research integrity**, not authenticated production
custody or independent access control. An operator with filesystem write access
could rewrite an entire chain; retained GitHub checkpoint hashes and external
review are therefore necessary. Public label exposure remains disclosed regardless
of event ordering. No production database/service is involved.

Run the independent golden and rejection tests with:

```bash
python -m pytest -q research/blueberry_vision/newtests/test_r3_splits.py
```

The cases include transitive leakage, exact/pending duplicate grouping, explicit
unknown identities, invalid/reference-missing GT, annotation changes after seal,
training/test leakage, publisher-exposed semantics, real-zero versus missing GT,
simulated review isolation, ledger ordering/tampering and source authority.
