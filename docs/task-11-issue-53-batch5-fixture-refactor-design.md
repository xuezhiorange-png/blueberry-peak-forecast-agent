# [TASK-011-INFRA][Batch 5] Test fixture and helper refactor — design freeze

**Status**: design-only freeze. This document does not modify any
test, fixture, helper, CI workflow, or production code. It does not
create `backend/tests/factories/`, `backend/tests/assertions/`, or
`backend/tests/db/` directories on disk.

Implementation requires a separate Charles authorization round after
this design PR is reviewed.

## Issue mapping

- Refs #53 (Batch 5 sub-issue, fixture refactor)
- Refs #23 (umbrella TASK-011-INFRA issue, sub-area 5)

Issue #53 remains open until a separate implementation PR is authorized,
merged, verified, and separately closed.
Issue #23 remains open as the umbrella until all 6 sub-areas (Batches
1-6) complete. Batch 5 closing only closes #53; #23 must not close.

This design uses only non-closing references.

---

## §1 Purpose

Per Issue #23 sub-area 5 ("Fixture refactor") and the Issue #53
sub-issue, this design proposes splitting the shared test helpers
currently scattered across multiple top-level `backend/tests/*.py`
modules into three explicit submodules with strict responsibility
boundaries:

- `backend/tests/factories/` — factory objects that compose test data
  by **calling** production canonical / hash / key / ID implementations
  under `backend/app/**`. Factories never reimplement canonical logic.
- `backend/tests/assertions/` — assertion helpers and matchers used
  across tests. Assertions never construct fixtures or open DB sessions.
- `backend/tests/db/` — DB connection management, isolation profile
  resolution, migration / concurrency isolation helpers, and
  test-identity (run-id / scope-id / canonical-payload-hash /
  audit-payload-hash) bookkeeping.

The current top-level helpers carry mixed responsibilities:

- `backend/tests/conftest.py` — root pytest plugin wiring.
- `backend/tests/concurrency_isolation_helpers.py` — DB isolation +
  test-identity types for concurrency-marked nodes.
- `backend/tests/migration_isolation_helpers.py` — DB isolation name
  resolution + safety predicates used by the dev-DB safeguard.
- `backend/tests/postgres_test_support.py` — PG session/engine helpers
  for integration tests.

Mixing factory, assertion, and DB concerns inside flat helper modules
makes import boundaries implicit, raises the risk that test-only
helpers accidentally drift away from production canonical implementations
(e.g. reimplementing a hash function), and complicates future pytest
shard mapping when CI ownership of fixture construction vs DB setup
diverges.

## §2 Scope

### 2.1 Goals

1. **Three-submodule split.** Move flat-helper content into three
   explicit `backend/tests/{factories,assertions,db}/` submodules with
   `__init__.py` files documenting each submodule's responsibility.
2. **Production-canonical reuse.** Test fixtures must **call** the
   production canonical / hash / key / ID implementations under
   `backend/app/**`. Test-only helpers may compose factory objects
   and assertions, but must never replicate canonical logic.
3. **Import-boundary discipline.** Imports between the three submodules
   follow the responsibility split below; arbitrary `factories` ↔
   `assertions` crossing is forbidden.
4. **Typed factory contract.** Both the DB identifier
   (`database_url` / port / role / profile name) and the test
   identity (run-id / scope-id / canonical-payload-hash /
   audit-payload-hash) become parts of an explicit typed factory
   contract, replacing implicit "first-arg-is-engine" conventions.
5. **Preserve PR #47 guardrails.** The dev-DB safeguard
   (`backend/tests/safety/test_dev_db_protection.py` +
   `backend/scripts/postgres_test_db.sh` + `Makefile test-pg` guard)
   continues to **fail closed** in CI and local dev. The one-command
   `make test-pg` contract remains.
6. **Preserve PR #67 marker taxonomy.** The Batch 4 marker taxonomy
   (`unit` / `contract` / `golden` / `postgres` / `migration` /
   `concurrency` / `e2e` / `slow` / `task8`-`task11`) and
   `ci-shard-manifest.yml` ownership rules remain unchanged in this
   design; the new submodules expose typed factories that already
   carry the correct markers via the existing per-shard ownership
   pattern.

### 2.2 Non-goals

- No production semantic change to TASK-011 evaluation, mask,
  canonical, hash, key, audit, or authority logic.
- No `backend/app/**` modification. Test fixtures call production
  canonical implementations but do not modify them.
- No Alembic schema change; `backend/alembic/versions/**` is forbidden.
- No `.github/workflows/**` modification; CI layout stays as
  PR #55 / PR #66 §3 defined.
- No `ci-shard-manifest.yml` mutation in this design. Any future shard
  edits required by the implementation round are described in §13
  as informational only and do NOT land in this PR.
- No `pyproject.toml` mutation. Pytest markers remain as Batch 4
  registered them.
- No test logic change. Existing tests continue to run unchanged
  semantically; the implementation PR rewires imports but does not
  alter test bodies, fixtures, or expected values.
- No CI de-duplication or marker taxonomy change (handled by
  Batches 2 and 4 respectively).
- No DB isolation strategy change (handled by Batch 3).
- No CI performance and diagnostics work (handled by Batch 6).
- No Makefile / bash script mutation. The `make test-pg` guard and
  `postgres_test_db.sh` safety checks remain as PR #47 introduced.

## §3 Baseline

Current baseline for this design is `main @ c9414d58cec54148654c8fc3485c5bfeb5d02f8e`
(squash merge of PR #67 / Batch 4 / Slice 1, post-merge CI run 28918632788
completed / success).

⚠️ **Note**: Issue #53 body references base
`main @ 41425234ad0664d678594473e792d4b909e44818` (the Batch 1 squash
merge commit). That base ref is **frozen at issue creation** and is now
stale relative to current `main`. The design PR base is the **current**
`main @ c9414d58cec54148654c8fc3485c5bfeb5d02f8e`, not the Issue #53
text's base ref.

Relevant completed prerequisites:

- Batch 1 / PR #47: local PostgreSQL test harness, dev-DB safeguard,
  `make test-pg` one-command contract. Squash merge commit
  `41425234ad0664d678594473e792d4b909e44818`, post-merge CI run
  `28833526725` completed / success.
- Batch 2 / PR #57 and PR #58: deduplicated PR CI layout, format
  baseline normalization. Issue #50 closed / completed.
- Batch 3 / PR #59 through PR #65: PostgreSQL database isolation
  strategy. Issue #51 closed / completed.
- Batch 4 / PR #67: pytest marker taxonomy registration, P1 manifest
  ownership fixup. Issue #52 closed / completed; squash merge
  `c9414d58cec54148654c8fc3485c5bfeb5d02f8e`; post-merge CI run
  `28918632788` completed / success.

Current shared helper landscape (top-level flat files at
`backend/tests/`):

| File | Primary responsibility (as currently mixed) | Target submodule |
|---|---|---|
| `backend/tests/conftest.py` | root pytest plugin wiring | kept at root; re-exports from new subdirs |
| `backend/tests/concurrency_isolation_helpers.py` | concurrency DB isolation + test-identity | `backend/tests/db/` (DB portion) + `backend/tests/factories/` (test-identity portion) |
| `backend/tests/migration_isolation_helpers.py` | migration DB isolation + safety predicates | `backend/tests/db/` (DB portion) + `backend/tests/db/safety.py` (safety predicates) |
| `backend/tests/postgres_test_support.py` | PG session / engine / profile helpers | `backend/tests/db/` |

Per-shard pytest marker ownership (Batch 4 carve-out, unchanged):

- `unit` / `contract` / `golden` (without `postgres`) → `unit-contract-golden`.
- `postgres` + `migration` → `postgres-migration`.
- `postgres` + `concurrency` (or legacy `postgres_concurrency`) → `postgres-concurrency`.
- `postgres` + `task11` → `postgres-task11` (with `-m "not postgres_concurrency"` exclusion).
- `postgres` + non-task11 domain files → `postgres-domain-1` / `postgres-domain-2`.

## §4 Target fixture / helper architecture

### 4.1 Top-level directory layout after implementation

```
backend/tests/
├── conftest.py                    # root pytest plugin wiring (unchanged role)
├── safety/
│   └── test_dev_db_protection.py  # PR #47 safeguard (unchanged location)
├── harvest_state/                 # TASK-011 evaluation / mask tests (unchanged)
├── integration/                   # postgres integration tests (unchanged)
├── analytics/                     # existing domain tests (unchanged)
├── baseline/                      # existing domain tests (unchanged)
├── etl/                           # existing domain tests (unchanged)
├── maturity/                      # existing domain tests (unchanged)
├── planning/                      # existing domain tests (unchanged)
├── residual_model/                # existing domain tests (unchanged)
├── rolling_backtest/              # existing domain tests (unchanged)
├── weather/                       # existing domain tests (unchanged)
├── test_*.py                      # existing root-level alembic / harvest state tests
│
├── factories/                     # NEW: factory objects composing production canonical
│   ├── __init__.py
│   ├── harvest_state.py           # compose HarvestStateRun + scope + identity
│   ├── residual_model.py          # compose ResidualModel artifacts
│   ├── baseline.py                # compose baseline fixtures
│   └── identity.py                # run-id / scope-id / canonical-payload-hash / audit-payload-hash builders
│
├── assertions/                    # NEW: assertion helpers and matchers
│   ├── __init__.py
│   ├── harvest_state.py           # assert block reasons / canonical match
│   ├── residual_model.py          # assert residual artifacts
│   ├── canonical.py               # assert canonical payload hash invariants
│   └── audit.py                   # assert audit payload hash invariants
│
└── db/                            # NEW: DB connection + isolation + profile
    ├── __init__.py
    ├── profile.py                 # APP_ENV=test / port 55432 / db_name resolution
    ├── isolation.py               # transaction + savepoint + rollback isolation (Batch 3 logic)
    ├── concurrency.py             # concurrency isolation (from concurrency_isolation_helpers.py)
    ├── migration.py               # migration isolation (from migration_isolation_helpers.py)
    ├── safety.py                  # safety predicates used by dev-DB safeguard
    └── session.py                 # PG session / engine / URL resolution (from postgres_test_support.py)
```

### 4.2 Responsibility split

| Concern | Owner | Forbidden to |
|---|---|---|
| Production canonical / hash / key / ID implementations | `backend/app/**` (unchanged) | Be re-implemented in `backend/tests/**` |
| Factory composition (test data + identities) | `backend/tests/factories/` | Open raw DB sessions; assert invariants directly |
| Assertion / matcher helpers | `backend/tests/assertions/` | Construct fixtures; open DB sessions; import from `factories/` for non-typed-arg convenience |
| DB connection / isolation / profile resolution | `backend/tests/db/` | Reimplement production canonical; compose fixtures; assert invariants |

### 4.3 Typed factory contract

The factory contract explicitly carries two typed inputs:

1. **DB identifier**: `database_url` / `port` / `role` /
   `profile_name` (e.g. `test-isolated`, `test-concurrency`,
   `test-migration`). The factory refuses to construct if the
   effective DB identifier does not match `APP_ENV=test` profile
   rules; this is the **second line** of defence after the
   `Makefile test-pg` guard and `postgres_test_db.sh` reject script.

2. **Test identity**: a typed tuple of
   `(run_id, scope_id, canonical_payload_hash, audit_payload_hash)`.
   The factory exposes these as constructor kwargs and reuses the
   production `compute_canonical_payload_hash` /
   `compute_audit_payload_hash` (or the canonical functions in
   `backend/app/**`) — never test-side reimplementations.

The contract is documented as a `Protocol` (or `TypedDict`) under
`backend/tests/factories/identity.py`, with a concrete
`HarvestStateFactory(identity=..., db_profile=...)` example.

## §5 Import-boundary rules

### 5.1 Allowed imports

- `backend/tests/factories/` MAY import:
  - `backend/app/**` (production canonical, hash, key, ID)
  - `backend/tests/db/` (DB profile / session — for fixtures that
    open engines, e.g. integration fixtures)
  - Standard library, pytest, sqlalchemy
- `backend/tests/assertions/` MAY import:
  - `backend/app/**` (production canonical, hash, key, ID for
    computing expected values)
  - Standard library, pytest
- `backend/tests/db/` MAY import:
  - `backend/app/**` (for typed DB identifier contracts and
    canonical hashing, when needed for assertions like
    "DB name encodes the run-id hash")
  - Standard library, pytest, sqlalchemy

### 5.2 Forbidden imports

- `backend/tests/assertions/` MUST NOT import from
  `backend/tests/factories/`. Assertions receive fixtures by
  argument, not by re-fetching them.
- `backend/tests/db/` MUST NOT import from
  `backend/tests/factories/` or `backend/tests/assertions/`. DB
  helpers are concerned only with connection / isolation / profile.
- `backend/tests/factories/` MUST NOT import from
  `backend/tests/assertions/`. Factories compose fixtures; they do
  not assert on them.
- All three submodules MUST NOT re-export `backend/app/**` names.
  Production canonical implementations remain in `backend/app/**`;
  test helpers call them, never shadow them.

### 5.3 Enforcement

The implementation PR adds a tiny **scope-guard test** under
`backend/tests/factories/test_import_boundaries.py` and
`backend/tests/db/test_import_boundaries.py` that reads each
submodule's `ast` and fails if a forbidden import is detected. The
guard is test-only and does not affect production imports.

## §6 Canonical / hash / key / ID production-logic reuse rule

The cardinal rule of this design is:

> **Test-only helpers MUST call the production canonical
> implementations under `backend/app/**` for any non-trivial
> canonical / hash / key / ID computation.**

"Non-trivial" includes:

- canonical payload hashing (`compute_canonical_payload_hash` or
  equivalent under `backend/app/**`)
- audit payload hashing (`compute_audit_payload_hash`)
- run-id / scope-id generation (any deterministic id derivation
  with salt / hash / counter logic)
- canonical serialization for `json.dumps(..., sort_keys=True,
  separators=(",", ":"))` style stable encoding
- deterministic ordering of records used for hashing
- key derivation (HMAC, sign, etc., if any)

"Trivial" includes:

- string formatting / f-strings for human-readable test labels
- integer / UUID generation for one-off identity markers in test
  data (when these are NOT subject to canonical-hash invariants)
- simple dataclass construction that mirrors but does not duplicate
  a production type

The implementation PR adds a scope-guard test
(`backend/tests/factories/test_no_canonical_reimplementation.py`)
that grep-scans `backend/tests/factories/` and
`backend/tests/assertions/` for forbidden hash / hmac / sign /
deterministic-uuid helper implementations and fails CI if any are
found. The grep scope is bounded by sentinel strings documented in
the implementation freeze (§13 carve-out) — same multi-slice
scope-guard sentinel pattern as `cold-storage-phase-implementation-governance`
documents.

## §7 Migration plan

The implementation PR follows a strict migration order to keep every
intermediate commit green:

1. **Commit 1: scaffold.** Create the three empty submodules with
   `__init__.py` files containing only module-level docstrings
   documenting responsibility. No helper moves yet.
2. **Commit 2: db/ migration.** Move `concurrency_isolation_helpers.py`
   DB portions, `migration_isolation_helpers.py` DB portions, and
   `postgres_test_support.py` into `backend/tests/db/`. Update
   `conftest.py` to re-export from new locations via compatibility
   shims (`backend/tests/concurrency_isolation_helpers.py` becomes a
   thin re-export module with a DeprecationWarning). Existing tests
   continue to import via old paths via the shim. CI green.
3. **Commit 3: factories/ migration.** Move test-identity portions
   into `backend/tests/factories/identity.py`. Update factories
   one domain at a time (harvest_state, residual_model, baseline).
   Each factory file declares `pytestmark = pytest.mark.<shard-marker>`
   so CI ownership is explicit. CI green per commit.
4. **Commit 4: assertions/ migration.** Move assertion helpers into
   `backend/tests/assertions/`. Tests continue to use old import
   paths via thin re-export shims. CI green.
5. **Commit 5: typed factory contract.** Introduce the typed
   factory contract (`Protocol` / `TypedDict`) and migrate
   existing factory call-sites one file at a time. CI green.
6. **Commit 6: scope-guard tests.** Add the
   `test_no_canonical_reimplementation.py` and
   `test_import_boundaries.py` guard tests. CI green.
7. **Commit 7: shim removal (optional).** If Charles authorizes a
   follow-up round, remove the compatibility shim modules and
   update all imports. CI green.

Each commit must independently pass all PR CI jobs (per PR #55 §3
8-job layout) and the `unit-contract-golden` job must continue to
discover the same set of test nodes as the pre-impl baseline.

## §8 Test strategy

### 8.1 Tests for the new submodules themselves

- `backend/tests/factories/test_factory_uses_production_canonical.py`
  — proves that a representative factory (e.g. `HarvestStateFactory`)
  delegates canonical hashing to `backend.app.*.compute_canonical_*`.
  Asserts the produced hash equals the value `backend.app.*`
  would produce for the same input.
- `backend/tests/factories/test_typed_factory_contract.py` — proves
  the typed factory accepts typed identity and DB identifier kwargs
  and refuses malformed inputs (e.g. `APP_ENV != test`).
- `backend/tests/factories/test_import_boundaries.py` — AST-based
  guard, see §5.3.
- `backend/tests/factories/test_no_canonical_reimplementation.py` —
  grep-based guard, see §6.
- `backend/tests/db/test_profile_resolution.py` — proves the new
  `db.profile` resolves `APP_ENV=test` / port 55432 / db name
  deterministically and refuses dev-DB overrides.
- `backend/tests/db/test_safety_predicates_unchanged.py` — proves
  the safety predicates used by `backend/tests/safety/test_dev_db_protection.py`
  behave identically before and after the move (golden comparison
  of boolean outcomes across representative inputs).
- `backend/tests/db/test_isolation_preserved.py` — proves Batch 3
  transaction + savepoint + rollback isolation works identically
  after the move.
- `backend/tests/assertions/test_matchers_consistent.py` — proves
  assertion matchers return identical booleans / messages before
  and after the move for a fixed input corpus.

### 8.2 Existing tests must continue to pass

Every existing test under `backend/tests/**` must continue to pass
with **identical results** (same number of pass / skip / fail, same
golden outputs). The compatibility shim in commit 2-4 ensures import
paths remain valid during the migration.

### 8.3 Marker taxonomy unchanged

Per Batch 4, new submodule tests carry the appropriate per-shard
`pytestmark = pytest.mark.<shard-marker>` declaration. Existing
markers remain; no new markers are introduced.

### 8.4 `ci-shard-manifest.yml` ownership update (informational)

The implementation round MAY add the new submodule files to
`ci-shard-manifest.yml` `owner_files` lists under the appropriate
shards (most likely `unit-contract-golden` for factory / assertion
contract tests and the existing postgres-* shards for DB tests).
This is **informational** in this design — no manifest change lands
in this design PR. Any manifest mutation must follow the existing
routing-only-disclosure pattern documented in
`ci-shard-manifest-ownership-gate` SKILL.md.

## §9 CI expectations

### 9.1 PR CI jobs (per PR #55 §3, unchanged)

| # | Job | Expected status |
|---|---|---|
| 1 | `static` | success |
| 2 | `unit-contract-golden` | success |
| 3 | `postgres-migration` | success |
| 4 | `postgres-domain-1` | success |
| 5 | `postgres-domain-2` | success |
| 6 | `postgres-task11` | success |
| 7 | `postgres-concurrency` | success |
| 8 | `compose-smoke` | success |
| 9 | `full-suite-canary` | skipped on `pull_request` per PR #55 §4 |

### 9.2 Test count parity

The implementation PR must preserve the test-node count delta
at ≤ 0 across all shards. Adding new scope-guard tests
(`test_factory_uses_production_canonical.py`,
`test_typed_factory_contract.py`, etc.) is allowed and counts as
+ nodes in the appropriate shard.

### 9.3 Green-CI gate per commit

Per §7 migration order, every commit must individually pass all
PR CI jobs. A commit that breaks CI is rolled back and re-applied.

## §10 Shard-manifest implications (informational only)

The implementation PR may need to update
`ci-shard-manifest.yml` to register new `owner_files` entries under
appropriate shards. Most likely additions:

- `unit-contract-golden` gains:
  - `backend/tests/factories/`
  - `backend/tests/assertions/`
  - `backend/tests/db/test_profile_resolution.py`
  - `backend/tests/db/test_safety_predicates_unchanged.py`
  - `backend/tests/factories/test_typed_factory_contract.py`
  - `backend/tests/factories/test_import_boundaries.py`
  - `backend/tests/factories/test_no_canonical_reimplementation.py`
- `postgres-migration` (or `postgres-task11`, depending on scope)
  gains `backend/tests/db/test_isolation_preserved.py` if it
  exercises Alembic.
- `postgres-concurrency` gains
  `backend/tests/db/test_concurrency_isolation_unchanged.py`
  if a like-for-like concurrency isolation regression test is
  added.

⚠️ **No manifest change lands in this design PR.** Manifest updates
require a separate implementation round and follow the
`ci-shard-manifest-ownership-gate` governance (D==M, lint triple,
mypy, pytest pre-push gates; routing-only-disclosure in PR body).

## §11 Acceptance gates

A future implementation PR is **accepted** when ALL of the following
are satisfied (verified before Charles's Ready authorization):

1. **All 8 PR CI jobs green** for the implementation head SHA.
2. **Test-node parity** (`git diff --shortstat <baseline>..<new>`
   shows file changes consistent with the migration plan; new
   scope-guard tests are listed and accounted for).
3. **No forbidden-path mutations** in the diff:
   - `backend/app/**` not modified.
   - `backend/alembic/versions/**` not modified.
   - `.github/workflows/**` not modified.
   - `pyproject.toml` not modified (unless minimal pytest marker
     additions are explicitly authorized, which they are NOT in
     this Batch 5 round — Batch 4 already finalized markers).
4. **No reimplemented canonical logic** — the
   `test_no_canonical_reimplementation.py` guard passes.
5. **No forbidden imports** — the `test_import_boundaries.py`
   guard passes.
6. **Dev-DB safeguard still passes** —
   `backend/tests/safety/test_dev_db_protection.py` still
   **fails closed** in CI and local dev.
7. **`make test-pg` contract still passes** — the one-command
   Makefile target still rejects dev-DB overrides with rc != 0.
8. **Shards are D==M-consistent** — `ci-shard-manifest.yml`
   discovery equals manifest-declared files (after implementation
   updates the manifest in its own commit per §10).
9. **Body freeze comment** posted at the implementation head SHA
   before Ready transition, per the standard 7-step verify recipe.

## §12 Rollback model and non-goals

### 12.1 Rollback

The implementation PR can be reverted with a single `git revert`
because:

- The migration is additive (new subdirs + thin re-export shims).
- No production semantic changes.
- No `backend/app/**` modifications.
- Compatibility shims keep old import paths valid until commit 7
  (shim removal).

If a future implementation commit breaks CI, the standard
"audit-preserving corrective fixup (Option A)" pattern from
`blueberry-phase-design-governance` applies: do NOT amend; append
a follow-on `fix(issue-53-...): ...` commit that resolves the break
while preserving the audit chain.

### 12.2 Non-goals (re-stated for implementation clarity)

- No `.github/workflows/**` mutation.
- No `backend/app/**` mutation.
- No `backend/alembic/versions/**` mutation.
- No `pyproject.toml` mutation.
- No `ci-shard-manifest.yml` mutation in this design PR. (Future
  manifest updates in implementation round are out of scope here.)
- No `Makefile` mutation.
- No `docker-compose*.yml` mutation.
- No `frontend/**` mutation.
- No production semantics changes (no TASK-011 evaluation / mask
  / canonical / hash / key / audit logic modifications).
- No CI de-duplication (Batch 2 done).
- No DB isolation redesign (Batch 3 done).
- No marker taxonomy overhaul (Batch 4 done).
- No CI performance and diagnostics (Batch 6).

## §13 Required implementation artifacts

A future Batch 5 implementation PR must update, at minimum:

- **Create**: `backend/tests/factories/__init__.py` +
  `backend/tests/factories/{identity,harvest_state,residual_model,baseline}.py`
- **Create**: `backend/tests/assertions/__init__.py` +
  `backend/tests/assertions/{canonical,audit,harvest_state,residual_model}.py`
- **Create**: `backend/tests/db/__init__.py` +
  `backend/tests/db/{profile,isolation,concurrency,migration,safety,session}.py`
- **Create**: `backend/tests/factories/test_factory_uses_production_canonical.py`
- **Create**: `backend/tests/factories/test_typed_factory_contract.py`
- **Create**: `backend/tests/factories/test_import_boundaries.py`
- **Create**: `backend/tests/factories/test_no_canonical_reimplementation.py`
- **Create**: `backend/tests/db/test_profile_resolution.py`
- **Create**: `backend/tests/db/test_safety_predicates_unchanged.py`
- **Create**: `backend/tests/db/test_isolation_preserved.py`
- **Create**: `backend/tests/assertions/test_matchers_consistent.py`
- **Modify (compat shim)**: `backend/tests/conftest.py` — re-export
  the moved helpers from new subdir locations.
- **Modify (compat shim)**: `backend/tests/concurrency_isolation_helpers.py` —
  become a thin re-export module with DeprecationWarning.
- **Modify (compat shim)**: `backend/tests/migration_isolation_helpers.py` —
  become a thin re-export module with DeprecationWarning.
- **Modify (compat shim)**: `backend/tests/postgres_test_support.py` —
  become a thin re-export module with DeprecationWarning.

Optional (only if Charles authorizes a follow-up round):

- Remove compat shim modules (commit 7 of §7).
- Update `ci-shard-manifest.yml` to add new `owner_files` entries
  (§10, informational only — NOT this design PR).
- Add `pytestmark = pytest.mark.<shard-marker>` to new submodule
  test files matching the existing per-shard ownership pattern.

The implementation PR must NOT mutate the design file
`docs/task-11-issue-53-batch5-fixture-refactor-design.md`.

## §14 Self-audit checklist for this design PR

- [x] Branch created from `main @ c9414d58cec54148654c8fc3485c5bfeb5d02f8e`.
- [x] Branch named `codex/issue-53-batch5-fixture-refactor-design`.
- [x] Only `docs/task-11-issue-53-batch5-fixture-refactor-design.md`
      is modified.
- [x] `backend/app/**` is NOT modified.
- [x] `backend/alembic/versions/**` is NOT modified.
- [x] `.github/workflows/**` is NOT modified.
- [x] `ci-shard-manifest.yml` is NOT modified (informational only in §10).
- [x] `pyproject.toml` is NOT modified.
- [x] `Makefile` is NOT modified.
- [x] `docker-compose*.yml` is NOT modified.
- [x] `frontend/**` is NOT modified.
- [x] No tests / fixtures / helpers are mutated.
- [x] `Refs #53` and `Refs #23` only; no `Closes` / `Fixes` / `Resolves`.
- [x] Issue #53 explicitly remains open.
- [x] Issue #23 explicitly remains open as umbrella.

## §15 Glossary and references

- **Issue #53**: [TASK-011-INFRA][Batch 5] Test fixture and helper refactor.
- **Issue #23**: [TASK-011-INFRA] umbrella (Optimize local PostgreSQL
  tests and CI execution), 6 sub-areas, sub-area 5 = fixture refactor.
- **PR #47 / Batch 1**: local PostgreSQL test harness, dev-DB safeguard,
  `make test-pg` one-command contract.
- **PR #55 / Batch 2 design**: CI de-duplication layout.
- **PR #57 / Batch 2 impl**: CI de-duplication implementation.
- **PR #59 - PR #65 / Batch 3**: PostgreSQL database isolation strategy.
- **PR #66 / Batch 4 design**: pytest marker taxonomy design freeze.
- **PR #67 / Batch 4 impl**: pytest marker taxonomy registration,
  squash-merged as `c9414d58cec54148654c8fc3485c5bfeb5d02f8e`.
- **Post-merge CI run 28918632788**: completed / success.
- **`ci-shard-manifest.yml`**: the single-execution ownership source of
  truth; routed through PR #55 §3 + Batch 4 §3.

## §16 Risk register

| Risk | Mitigation |
|---|---|
| Compatibility shim breaks a hidden import path | Per-commit CI run; revert-on-break |
| Production canonical implementation is duplicated by mistake in `factories/` or `assertions/` | `test_no_canonical_reimplementation.py` grep guard |
| `backend/app/**` accidentally modified | `git diff --stat <baseline>..<impl>` reviewed before commit; CI lint + mypy as defense |
| Submodule imports cross `factories` ↔ `assertions` | `test_import_boundaries.py` AST guard |
| `ci-shard-manifest.yml` ownership drifts (D != M) | Implementation round adds new entries per §10; `verify-manifest` gate catches drift |
| Dev-DB safeguard regressed | `test_dev_db_protection.py` (PR #47) re-run unchanged; same outcome required |
| `make test-pg` contract breaks | Implementation round must NOT touch `Makefile` / `backend/scripts/postgres_test_db.sh` |
| Issue #23 accidentally closes via this PR | PR body uses `Refs #23` only (no `Closes`); this design says "Issue #23 remains open as umbrella" explicitly |
| Issue #53 accidentally closes via this PR | PR body uses `Refs #53` only (no `Closes`); this design says "Issue #53 remains open" explicitly |

## §17 Open questions frozen at design stage

None. The implementation choices in §4-§8 are concrete and the
migration plan in §7 is commit-by-commit deterministic.

Future follow-up rounds (out of scope for this design):

- Shim removal round (commit 7 of §7).
- Manifest registration round (§10).
- Typed factory contract extension to additional domains
  (e.g. `analytics`, `baseline` factories).

## §18 Change log

| Date | Change | Author |
|---|---|---|
| 2026-07-08 | Initial design freeze against `main @ c9414d58cec54148654c8fc3485c5bfeb5d02f8e` | Codex (design freeze round, post-PR #67 merge) |