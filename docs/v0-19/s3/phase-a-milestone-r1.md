# V0.19 S3 Phase A milestone R1

Task: `V0_19_S3_REAL_PHASE_A_MILESTONE_R1`.
Reviewed main: `1bd00af5a9027a21574dfbd76b9fbafb5a2f19c4`.
Main CI: `39778110336`, completed/success. This is not this PR's CI.

## Delivered wiring, not real execution permission

Existing algorithms, full-support calculation, admitted-Base filtering, failed-member
inventory and ten-metric scoring are unchanged. No Phase B permission is added.
The same engine is exercised with the existing full-size fictional fixtures.

`phase_a_subject` canonically hashes the operation, formal C0 payload seal, exact
absolute input Manifest path and file hash, current code identity and restrictions.
An `A_EXECUTION` signature over just a C0 hash no longer suffices. Execution requires:

1. Independent Reviewer `IMPLEMENTATION_REVIEW` of current code.
2. Independent Reviewer `C0_SEAL_REVIEW` of that exact execution subject.
3. Owner `A_EXECUTION` of the same subject, separately issued and time-limited.
4. Existing PROTOCOL, FORMAL_C0 and A_INPUT_READ decisions and all frozen input checks.

CLI gates run before C0/input access; the engine repeats the checks before computation
and before releasing a seal. Independent recomputation verifies the recorded grants
at the recorded execution time as well as current trusted enrollment. Signatures
cannot be substituted across roles, code identities, C0s or manifests.

## Real custody remains blocked

The previous public enrollment and all old evidence are unchanged. Its two keys
remain under one OS user's custody. Different key bytes do not prove independent
custody. No Reviewer decision or real A_EXECUTION was signed in this task.

The new optional `--real-phase-a-enrollment` requires exact, reviewed public bytes.
`REAL_PHASE_A_ENROLLMENT_SHA256` intentionally remains **None** until an actual
independent Reviewer and custody evidence are supplied and independently reviewed.
There is no runtime hash override, environment flag or approval Boolean. Adding the
pin is a reviewed code change, not a way for an operator to enroll arbitrary keys.

Enrollment schema: version 1, mode REAL, Owner scope R1, parent enrollment SHA256,
issued_at/expires_at, existing Owner key ID, new Reviewer key ID/public key,
distinct Owner/Reviewer custodian IDs, custody evidence SHA256. The Reviewer key
cannot be either prior same-custodian key. A field declaring different custodians
is not proof: the pinned record must first have genuine external evidence.

Only Owner A_EXECUTION and Reviewer C0_SEAL_REVIEW are added to the prior role
capabilities. B_LABEL_READ and B_SCORING remain denied even with an Owner signature.
Tests temporarily pin fictional enrollment only inside isolated pytest fixtures;
they never install real trust or open the five private inputs as test data.

## Read-only actual metadata verification

Reopened only the already authorized five files and prior C0 metadata. No label,
private key, original harvest workbook or database was opened. All five frozen
hashes match. Exact member/calendar/source comparison confirms 39 Base, H7 9672,
H15 9360, no missing/replaced/rejected registered members. This does not undo the
four research exclusions or establish physical equivalence/strict PIT.

Historical C0 seal:
`d5dc13b119357934ddcbcf3abd5fbef413ffbfecc87035734ba4f2fcf93d4b2a`.
Approved member-set hash:
`50a2dd0ae913920fb32515c5a1fb41c0c62cc90217bd66bd5a9686c912a9df13`.
Private audit report hash:
`c6694991519a7880658972c40eb328ce83c7173c44d5fb24e31c358aaa42a0e2`.

The old signatures were verified against their actual historical Git code bytes,
not silently accepted against new code. Candidate fields other than code identity
remain identical. The old C0 remains a valid historical record; activation on final
new code requires explicit re-binding and independent review. No new real C0,
Reviewer signature, or A_EXECUTION was generated. Private report directory is 0700,
report 0600, exclusive new path; old files were not overwritten.

## One bounded operating handoff

After independent custody enrollment is genuinely established and pinned, freeze
the final code identity, then re-bind the approved unchanged members/input Manifest
to that code. Preserve old records. Reviewer checks the code, five inputs, formal
seal, 19032 members, A/B isolation and absence of B permissions and signs the two
reviews. Only a later explicit Owner execution decision may sign A_EXECUTION.
The signatures' payloads include current code identity, exact subject, restrictions,
key ID, decision ID and timezone-aware validity interval.

Future command template (not executed with real files):

```sh
python -m backend.research.v019_research_cli stage-a --mode REAL \
  --real-trust-config "$PARENT_ENROLLMENT" --real-phase-a-enrollment "$REVIEWED_ENROLLMENT" \
  --grants "$SIGNED_GRANTS" --formal "$FORMAL_C0" --formal-hash "$C0_SHA256" \
  --inputs "$INPUT_MANIFEST" --inputs-hash "$MANIFEST_SHA256" --output "$NEW_PRIVATE_A_DIR"
python -m backend.research.v019_research_cli verify-a --mode REAL \
  --real-trust-config "$PARENT_ENROLLMENT" --real-phase-a-enrollment "$REVIEWED_ENROLLMENT" \
  --grants "$SIGNED_GRANTS" --formal-hash "$C0_SHA256" \
  --inputs "$INPUT_MANIFEST" --inputs-hash "$MANIFEST_SHA256" \
  --seal "$A_SEAL" --seal-hash "$A_SEAL_SHA256" --output "$NEW_PRIVATE_VERIFY_DIR"
```

Use distinct, new owned private output directories (0700/files0600); existing
writer rejects overwrite. `verify-a` accepts no labels and checks exact scope before
independent numerical recomputation. Its result is technical verification, **not**
a human review signature. Retain full seal, member failures and manifest; do not
discard unsuccessful samples. Store real executed_at, never backfill historical
issuance. Complete support remains 2025-07-01..2026-04-15, followed by H7/H15 slicing,
not window-specific normalization. Origin/cutoff remains Asia/Shanghai D0 end/D1.

## Validation and limits

Local results and immutable private receipt hashes are in the accompanying JSON;
final PR commit and exact-head Actions results are supplied by GitHub, not a stale
main run. Original numerical snapshots, full/partial/no-admission tests, label
isolation, failure denominators and strict PIT tests remain asserted.

Final stable-source local run: **534 passed, 0 failed, 0 skipped, 243.13 seconds**.
Ruff, Format and Mypy pass for all seven changed Python files. This includes real
mode authorization verification with fictional pinned keys and the full synthetic
39-Base C0→A→independent verify-a→B/report process chain. It does not claim a real
Reviewer has accepted this implementation or that private real Phase A ran.

Development history retained: two new tests initially failed on missing wiring;
an old missing-label fixture needed newly scoped signatures after changing its
Manifest path; an intermediate run detected code-identity drift while CLI editing
was still in progress (503 passed, 31 fixture errors). That run is not acceptance.
The final run uses stable source bytes. No skip, xfail, retry or relaxed assertion.

REAL_PHASE_A_READY=BLOCKED. Independent custody, actual implementation/C0 reviews,
final-code operational re-binding, and later Owner execution permission remain open.
No real prediction, scoring, training, deployment, Ready or Merge was performed.
