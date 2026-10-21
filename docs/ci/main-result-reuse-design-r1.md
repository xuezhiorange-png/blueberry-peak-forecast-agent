# Main CI result reuse: design only

Task: `BLUEBERRY_CI_FULL_COVERAGE_ACCELERATION_R1`, phase 2.
Status: **PROPOSED_NOT_ENABLED**. This document grants no change to main gates,
GitHub required checks, merge permissions or deployment authority.

## Candidate reuse evidence

A future separately reviewed implementation could consider reuse only when a
trusted GitHub provenance chain proves all of the following, not from a PR's
self-declared JSON or an arbitrary green status:

1. Repository ID, workflow ID/path, triggering event, exact PR head, run ID and
   attempt, authenticated Actions artifacts and job conclusions are known.
2. Every required check and exhaustive worker/gate actually succeeded. Missing,
   skipped, cancelled, timed-out, failed or neutral required work is ineligible.
3. The actual main commit Git tree equals the tested PR checkout/merge tree.
   Equal PR head names or equal-looking diffs do not prove tree equality.
4. The trusted workflow and helper blobs, lockfile, constraints and project
   dependency declarations are identical and were independently reviewed.
5. Installed dependency versions, Python version, runner OS/image, PostgreSQL
   version/image, Node/Playwright/browser and relevant native/TLS tooling match.
   Unrecorded image tags or environment identity are insufficient.
6. The test catalog, execution/outcome proof, full JUnit, fixture/command flags,
   source identity and security configuration cover the intended main checks.
7. The merge parent/base chain is reconciled. Base drift, intervening changes,
   changed inputs or unprovable squash/rebase provenance trigger full execution.
8. Artifact retention, integrity and provenance are valid for that exact attempt.
   A successful rerun cannot use stale artifacts from an earlier failed attempt.
9. Differences in PR/main secrets, permissions, event-controlled fixtures or
   external services have been explicitly assessed. Tree equality alone is not
   environment or behavior equality.

The minimum runner/image evidence is not fully available in today's proof, so
the current proof format is **not** sufficient to activate this policy.

## Mandatory full-test fallbacks

| Situation | Proposed behavior |
| --- | --- |
| Direct push, unknown originating PR or untrusted artifact producer | Full suite |
| Base/merge/tree mismatch or missing parent evidence | Full suite |
| Workflow, dependency, native library, image or environment drift | Full suite |
| Missing/expired/corrupt evidence or wrong run attempt/head | Full suite |
| Failed/cancelled/skipped/partial previous run | Full suite |
| Nightly scheduled run | Full suite, even if a recent PR was green |
| Manual dispatch or explicit diagnostic request | Full suite by default |
| New evidence format/policy not independently accepted | Full suite |

Fallback must be automatic and operational, not a green "reuse unavailable"
message. Inability to execute the fallback must fail the required check.

## Required checks and trust boundary

The externally required `full-suite-canary` check must always represent an
actually executed trusted validation job. Do not replace it with skipped
workflow status, a client-supplied success, a missing check, or an unvalidated
matrix `needs` result. A future policy would need explicit branch-protection
review, least-privilege Actions access, artifact attestation verification,
audit logs explaining reuse versus full fallback, and negative integration tests
for every rejection case. Approval of an engineering check never authorizes
Ready/Merge, real data access, model promotion, release or deployment.

PR-controlled workflow changes must not be allowed to mint their own trusted
reuse evidence. The trusted validator/policy would need an independently
approved source and protection, not merely a matching workflow hash copied from
the untrusted candidate. The current PR does not implement that infrastructure.

## Measurement and rollout proposal

First collect complete parallel-canary acceptance evidence. Then, only after
separate Owner approval, run a shadow decision alongside mandatory main full
tests, measure false accepts/rejects and actual saved runner minutes, and obtain
independent review. No shadow PASS would suppress a main test. Activation,
rollback criteria and required-check migration would require another explicit
decision. This phase remains a proposal; main push, nightly and dispatch keep
their full test gates now.
