# Owner-controlled retrospective execution

Task: `V0_19_S3_OWNER_CONTROLLED_REAL_REPLAY_R1`.
Base: `3a877fea38978bc7717bb36914ec77e2151f8f0c`.

The current Owner instruction expressly changes this local research authorization
policy. `OWNER_CONTROLLED_RETROSPECTIVE` is a separate CLI, not fabricated Reviewer
signatures and not a change to the signed CLI or production strict-PIT evaluator.
Its authorization boundary is the Owner's local OS account invoking the named
task command (including execution delegated to Codex in the current instruction).
It is not an authentication service and does not claim to protect against an
adversary already controlling that account or to prove third-party acceptance.

The dedicated `backend.research.v019_owner_replay` command accepts only the fixed
2025–2026 source scope. REAL manifest, five file hashes, prior C0 payload seal and
exact approved membership hash are fixed. Rebinding compares every candidate
field except the deliberately updated source-code identity, verifies the old
review and approved set, and creates a new seal without overwriting old records.
No count-only admission, fuzzy mapping, re-fitting or window normalization occurs.

`stage-a` has no label argument. It uses existing full-support calculation once
per admitted Base and preserves all member failures. `verify-a` recomputes in a
separate process and outputs an exact seal-bound receipt. `stage-b` requires that
receipt and independently verifies A again before opening the exact pinned
Owner-scope daily SOURCE_002 derivative. No other label source is discovered.
All per-day authority fields must match the sealed metadata. Missing/invalid rows
remain non-computable; they are never silently zero-filled. The existing metric
core is shared with the signed route without changing formulas or denominators.

Every output bundle records the actual command, UTC time, Git SHA, source digest,
data class, task authorization provenance and content hashes. Directories are
0700 and files 0600, exclusive creation. Real execution requires clean committed
source. The explicit synthetic route accepts only existing reviewed fictional
file identities and cannot relabel the actual private files.

Example stages (explicit absolute paths and file hashes required):

```sh
python -m backend.research.v019_owner_replay stage-a \
  --owner-command V0_19_S3_OWNER_CONTROLLED_REAL_REPLAY_R1 --data-class REAL \
  --inputs "$INPUT_MANIFEST" --inputs-hash "$INPUT_SHA" \
  --historical-c0 "$OLD_C0" --historical-c0-file-hash "$OLD_C0_FILE_SHA" \
  --output "$NEW_A_DIR"
python -m backend.research.v019_owner_replay verify-a \
  --owner-command V0_19_S3_OWNER_CONTROLLED_REAL_REPLAY_R1 --data-class REAL \
  --seal "$A_SEAL" --seal-file-hash "$A_FILE_SHA" --output "$NEW_VERIFY_DIR"
python -m backend.research.v019_owner_replay stage-b \
  --owner-command V0_19_S3_OWNER_CONTROLLED_REAL_REPLAY_R1 --data-class REAL \
  --seal "$A_SEAL" --seal-file-hash "$A_FILE_SHA" \
  --verification "$VERIFY_RECEIPT" --verification-file-hash "$VERIFY_FILE_SHA" \
  --labels "$PINNED_DAILY_ARTIFACT" --labels-hash "$DAILY_SHA" --output "$NEW_B_DIR"
```

SOURCE_002 is **recorded raw-fruit inbound weighing net weight**, not proof of all
field harvest. The existing internal physical-basis code is retained for schema
compatibility, with this explicit meaning in the report. Training-label physical
equivalence, historical area known-at and historical issuance remain unproved.
The study is RETROSPECTIVE_REPLAY / EXPOSED_HISTORICAL_BENCHMARK, STRICT_PIT=false;
not production accuracy, blind OOT, model promotion or full-season admission.
H7/H15 overlapping windows retain S1 weighting; they are not independent trials.

Real input data and result bundles are private local artifacts, never committed.
Execution results and CI are reported separately; code presence is not evidence
that real computation or independent acceptance occurred.
