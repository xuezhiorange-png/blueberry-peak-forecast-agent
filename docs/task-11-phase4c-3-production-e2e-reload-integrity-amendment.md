# TASK-011 Phase 4c-3 — Design Amendment: Production-shaped E2E and Reload Integrity

> **Status:** Design-only. **Not** implementation. **Not** migration. **Not** production code. **Not** implementation tests.
> **This PR does NOT implement 4c-3 code, modify tests, or create migrations.** It freezes the 4c-3 contract only.
>
> **This amendment depends on Phase 4a (frozen) + Phase 4b (frozen) + Phase 4c design amendment (frozen) + Phase 4c-1 service layer (MERGED) + Phase 4c-2 CLI + deterministic export (MERGED) as design + implementation inputs.**

---

## 0. Header / Status

- **Phase 4c-3 is design-only.** It freezes the contract for production-shaped E2E and reload integrity. Implementation is NOT authorized in this PR.
- **This PR does NOT implement 4c-3 code.** No source file under `backend/app/rolling_backtest/` is touched.
- **This PR does NOT modify implementation tests.** No new test file is added.
- **This PR does NOT create migrations.** No Alembic revision is added.
- **This PR does NOT create API code, frontend code, or HTTP / WebSocket / GraphQL code.**
- **Phase 4c-3 depends on**:
  - Phase 4a design amendment (frozen via PR #35)
  - Phase 4b design amendment (frozen via PR #37)
  - Phase 4b implementation (MERGED via PR #40)
  - Phase 4c design amendment (frozen via PR #41; content SHA `9f1f541367ee7c4ea3814f0068f682b29e590758690dcb2098cadd5de7796216`)
  - Phase 4c-1 service layer (MERGED via PR #42)
  - Phase 4c-2 CLI + deterministic export (MERGED via PR #44; merge commit `a3a65e9097dca886d655c3e52e1c0234d606d9fd`)
- **PR must remain Draft** until Charles explicitly authorizes freeze + Ready.
- **Implementation split (binding):**
  - **4c-3 design** (this PR) — contract only.
  - **4c-3 implementation** — future slice, requires separate Charles authorization, requires separate Draft PR.

---

## 1. Dependency anchors

- **main SHA**: `a3a65e9097dca886d655c3e52e1c0234d606d9fd` (post-PR-#44-merge)
- **PR #41 merge commit (Phase 4c design amendment)**: see git history
- **PR #42 merge commit (Phase 4c-1 service layer)**: see git history
- **PR #44 merge commit (Phase 4c-2 CLI + export)**: `a3a65e9097dca886d655c3e52e1c0234d606d9fd` (MERGED 2026-07-06T15:43:33Z)
- **PR #44 head SHA**: `3de79d599dd3282515b5762baf6142be5035fb55`
- **Phase 4c Design Amendment Content SHA**: `9f1f541367ee7c4ea3814f0068f682b29e590758690dcb2098cadd5de7796216` (preserved, not rotated)
- **Phase 4b Design Amendment Content SHA**: `7ed7cb567c72f107b4a83ed64f0ed66309fdd98049110afa4ec3831598e7c63a` (preserved, not rotated)
- **Phase 4a Design Amendment Content SHA**: `632e2e1f2880c9a6d7b87ee9f90565223ece69aaee43bea620f526c1fe1c8f3c` (preserved, not rotated)
- **Phase 4b metric definition version**: `4b-1.0.0` (frozen at `backend/app/rolling_backtest/metrics.py`)
- **Phase 4c-2 CLI version**: `4c-2.0.0` (frozen at `backend/app/rolling_backtest/cli.py`)
- **Issue #43 (Phase 4c-2 tracking)**: CLOSED / COMPLETED (closeout comment `4895013757`); MUST remain CLOSED
- **Post-PR-#44 main CI**: Run `28804025311` — completed / success / `headSha=a3a65e9…` exact match

### 1.1 Refs

- Issue #21 — TASK-011 umbrella, CLOSED / COMPLETED
- Issue #33 — Phase 4 planning, CLOSED / COMPLETED
- Issue #36 — Phase 4b planning, CLOSED / COMPLETED
- Issue #38 — Phase 4c planning, CLOSED / COMPLETED
- Issue #43 — Phase 4c-2 tracking, CLOSED / COMPLETED (closeout comment `4895013757`)
- Issue #23 — postgres test infra, OPEN, infra track (separate from 4c-3)
- PR #24 — postgres test infra draft, CLOSED / draft / not merged, infra track (separate from 4c-3)
- PR #35 — Phase 4a design amendment, MERGED
- PR #37 — Phase 4b design amendment, MERGED
- PR #40 — Phase 4b implementation, MERGED
- PR #41 — Phase 4c design amendment, MERGED
- PR #42 — Phase 4c-1 service layer implementation, MERGED
- PR #44 — Phase 4c-2 CLI + export implementation, MERGED (merge commit `a3a65e9097dca886d655c3e52e1c0234d606d9fd`)

---

## 2. Phase 4c-3 scope boundary

### 2.1 In scope (4c-3 contract freeze)

- **Production-shaped E2E contract** — defines the input fixture / materialization shape, the service-layer `compute_metrics` consumption, the CLI `compute-metrics` invocation, the JSON / CSV / manifest / audit artifact generation, and the post-run artifact verification.
- **Reload integrity contract** — defines the manifest-first reload path, the `canonical_payload_hash` verification, the `audit_payload_hash` verification, the CSV ↔ JSON row consistency check, the manifest path integrity check, and the deterministic byte-level expectations where applicable.
- **Provenance chain contract** — links Phase 4a materialization identity → Phase 4b metric output identity → Phase 4c-1 service result identity → Phase 4c-2 export artifact identity → Phase 4c-3 reload verification identity.
- **Failure / blocker model** — enumerates and binds the error / blocker kinds for 4c-3: missing artifact, malformed JSON, malformed CSV, manifest mismatch, hash mismatch, audit mismatch, row-order mismatch, metric-definition-version mismatch, mask-hash mismatch, forbidden implicit fallback.
- **Test contract** — defines the 4c-3 test surface as contract descriptions only (NOT implementation): production-shaped E2E happy path, reload from manifest, JSON / CSV consistency check, audit hash check, deterministic re-run check, negative tests for corrupted artifact / hash / path, no database / network side channel beyond explicitly authorized fixture / provider boundary.
- **Implementation split** — design-only in this PR; future implementation requires separate Charles authorization and a separate Draft PR.

### 2.2 Out of scope (binding for any 4c-3 implementation)

- Phase 4a materialization redefinition (frozen; do not touch).
- Phase 4b metric formula redefinition (frozen; do not touch).
- Phase 4c-1 service layer redefinition (MERGED via PR #42; do not touch).
- Phase 4c-2 CLI / export redefinition (MERGED via PR #44; do not touch).
- Task 8 / Task 9 / Task 10 semantic changes.
- Task 10 `replay_trained_model` (explicitly DEFERRED; do not touch).
- Model training changes.
- Database migrations (Alembic revisions) — unless a separately authorized schema-gap amendment explicitly opens that scope.
- API endpoint implementation — `backend/app/api/` must not be touched by 4c-3.
- Frontend / HTTP / WebSocket / GraphQL implementation.
- Implicit `current` / `latest` / `most recent` selection (forbidden across all 4c-3 surfaces).

---

## 3. Production-shaped E2E contract (§§3.1 – 3.5)

The 4c-3 E2E contract is the "production-shaped" test of the full 4c stack (4a materialization → 4b metrics → 4c-1 service → 4c-2 CLI / export) wired together with no production shortcuts. It is **not** a substitute for true production deployment; it is the highest-fidelity pre-production verification.

### 3.1 Input fixture / materialization shape

- **Materialization shape** MUST match the Phase 4a frozen `EvaluationMetricRow` schema exactly (frozen via `docs/task-11-phase4a-evaluation-mask-amendment.md`).
- **Materialization identity** MUST be carried by `(run_id, evaluation_mask_hash)` exactly as bound by Phase 4a.
- **Fixture source** MUST be a deterministic, byte-stable artifact (e.g. a JSON file or a `pytest` fixture) that the E2E test loads without going through a network / database IO boundary. The fixture boundary is the only place where test data enters the 4c stack; beyond that boundary the 4c stack is exercised exactly as it would be in production (no internal mocking).
- **Mask binding** MUST be explicit: the test wires the `(run_id, evaluation_mask_hash)` to a stub materialization provider (per 4c-1 §3.2 contract); the provider returns the fixture rows.

### 3.2 Service-layer `compute_metrics` consumption

- The E2E test MUST call `compute_metrics(...)` directly (the 4c-1 service-layer entry point, MERGED via PR #42) with the full Phase 4a / Phase 4b request shape.
- The test MUST verify that `EvaluationResult.canonical_payload_hash` is byte-identical for byte-identical inputs (determinism binding to Phase 4b).
- The test MUST verify the `EvaluationResult.outputs` ordering matches the Phase 4b canonical order (counters first, then aggregate metrics).

### 3.3 CLI `compute-metrics` invocation

- The E2E test MUST invoke the CLI as a subprocess (`python -m backend.app.rolling_backtest.cli compute-metrics …`) so that the entry-point binding of §4.1 is exercised exactly as a user would.
- The CLI argv MUST include all required flags per §4.2 (`--run-id`, `--scope`, `--mask-hash`, `--output-dir`).
- The CLI exit code MUST be one of `{0, 3}` (success or `MetricBlocker`; per §4.3 and §4.5) for a well-formed request.
- The CLI stdout MUST be parseable as a single-line JSON object with the documented success / blocker keys.

### 3.4 JSON / CSV / manifest / audit artifact generation

- The CLI MUST write four files under `<output-dir>/{json,csv,manifest,audit}/` (per §5.4) with the frozen filename pattern `<run-id>__<scope-id>__<hash>.<ext>` (per §6.1).
- The JSON file MUST have the §5.1 frozen top-level keys (lexicographic order), `metric_definition_version = "4b-1.0.0"`, `cli_invocation` present iff audit is enabled, and `canonical_payload_hash == EvaluationResult.canonical_payload_hash`.
- The CSV file MUST have the §5.2 frozen header order, LF-only line terminators, UTF-8 no BOM, and `null` → empty-cell binding.
- The manifest file MUST have the §5.3 frozen top-level keys (lexicographic order), `canonical_payload_hash == EvaluationResult.canonical_payload_hash`, and `audit_payload_hash == SHA-256(audit bytes)` (or `null` when `--no-audit` is set).
- The audit file MUST have the §4.4 / §7.1 frozen key set, `command_invocations` reflecting `main(argv=...)` (not `sys.argv[1:]`; per round-2 P1 fix), and `metric_definition_version = "4b-1.0.0"`.

### 3.5 Post-run artifact verification

- The E2E test MUST re-read the four artifacts from disk (no in-memory shortcut).
- The test MUST verify each artifact's byte-level content (or content hash) matches the expected pre-recorded expected values for the same input fixture.
- The test MUST assert that the four files' `canonical_payload_hash` and `audit_payload_hash` form a consistent graph (manifest's `canonical_payload_hash` matches JSON's, manifest's `audit_payload_hash` matches SHA-256 of the audit file bytes).

---

## 4. Reload integrity contract (§§4.1 – 4.6)

The 4c-3 reload integrity contract specifies how a downstream consumer (a future API slice, a future audit tooling slice, a future reload-into-database slice) verifies that a previously-written 4c-2 artifact set is still trustworthy and unmodified.

### 4.1 Manifest-first reload path

- The reload entry point MUST be the **manifest file** (per §5.3). A consumer reads the manifest first, extracts the relative paths to JSON, CSV, and (optionally) audit, then reads those files.
- The reload MUST NOT require the original `compute_metrics` invocation context. The manifest is the self-contained provenance record.
- The reload MUST be **stateless**: the verifier does not need to re-run any compute; it reads the artifacts and verifies their content.

### 4.2 `canonical_payload_hash` verification

- The reload MUST recompute `canonical_payload_hash` from the JSON file's `outputs` array (using the Phase 4b `canonical_payload_hash` primitive; preserved unchanged per 4b-1.0.0) and assert it equals the manifest's `canonical_payload_hash`.
- A mismatch MUST surface as `ServiceContractError(kind="canonical_payload_hash_mismatch", ...)` (proposed binding; see §5 for the full kind list).

### 4.3 `audit_payload_hash` verification

- When the manifest's `audit_payload_hash` is non-null, the reload MUST recompute `SHA-256(audit_bytes)` and assert it equals the manifest's `audit_payload_hash`.
- A mismatch MUST surface as `ServiceContractError(kind="audit_payload_hash_mismatch", ...)` (proposed binding; see §5).

### 4.4 CSV ↔ JSON row consistency

- The reload MUST parse the CSV file and assert that the metric_name column (column 0) matches the JSON file's `outputs[*].metric_name` array, in the same order.
- The reload MUST assert that the CSV row count equals `len(JSON.outputs)`.
- A mismatch MUST surface as `ServiceContractError(kind="row_order_mismatch", ...)`.

### 4.5 Manifest path integrity

- The reload MUST assert that each path in the manifest (`json_path`, `csv_path`, `manifest_path`, `audit_path`) resolves to a file under the reload's root directory, and that the file exists.
- A missing file MUST surface as `ServiceContractError(kind="missing_artifact", ...)`.

### 4.6 Deterministic byte-level expectations

- Where the E2E test pre-records expected file bytes (e.g. via a snapshot fixture), the reload MUST byte-compare the reloaded artifact against the snapshot. The snapshot fixture itself MUST be byte-stable across test runs (no timestamps in the snapshot; the only allowed timestamp is the audit file's `started_at_utc` / `finished_at_utc`, which is allowed to differ).
- The byte-comparison MUST NOT use the audit file as a stable-comparison target (because audit timestamps vary); the audit MUST be verified via `audit_payload_hash` instead (per §4.3).

---

## 5. Provenance chain contract (§5.1 – 5.5)

The provenance chain binds the identity of every artifact in the 4c stack to its upstream origin. Each link MUST be verifiable independently.

### 5.1 Phase 4a materialization identity

- The `evaluation_mask_hash` (64-char lowercase hex) is the Phase 4a materialization identity at the leaf. The `run_id` is the Phase 4a logical-run identity. Both MUST be present in the JSON and audit top-level fields, and in every `MetricOutput.evaluation_mask_hash` and `metric_scope_identity`.

### 5.2 Phase 4b metric output identity

- Each `MetricOutput` carries a `metric_scope_identity` (per 4b-1.0.0) that is bound to the `evaluation_mask_hash` and the `scope` dict. The identity is the SHA-256 of the canonicalized `scope` payload. The JSON and CSV files MUST carry this identity on every output row.

### 5.3 Phase 4c-1 service result identity

- `EvaluationResult.canonical_payload_hash` is the Phase 4c-1 / Phase 4b binding identity. It MUST be present in the JSON, manifest, and audit files (and in the stdout success / blocker JSON). A future verifier MUST be able to re-derive this hash from the JSON's `outputs` array and assert it matches the manifest's value.

### 5.4 Phase 4c-2 export artifact identity

- The manifest's `audit_payload_hash` is the Phase 4c-2 binding identity for the audit file. The manifest itself carries `canonical_payload_hash` (which is the 4c-1 / 4b identity, not a 4c-2 identity) and `metric_definition_version` (which is a 4b identity).

### 5.5 Phase 4c-3 reload verification identity

- The reload verification does NOT introduce a new hash. It reuses the existing 4c-1 / 4c-2 / 4b identities: `canonical_payload_hash`, `audit_payload_hash`, `metric_definition_version`, `evaluation_mask_hash`, `metric_scope_identity`. A 4c-3 verification run is itself recorded in an audit file (per the §3.3 E2E shape), so its own `command_invocations` and `started_at_utc` are recorded for downstream consumers.

---

## 6. Failure / blocker model (§§6.1 – 6.10)

The 4c-3 surface MUST distinguish the following error / blocker kinds. Each is a `ServiceContractError`-compatible class (a subclass or a structured payload) carrying the documented fields. The kinds are bound to the 4c-3 contract and are additive to the existing 4c-1 kinds.

### 6.1 `missing_artifact`

- **When:** a reload expected a file (json / csv / manifest / audit) at the path recorded in the manifest, but the file does not exist.
- **Carries:** `path` (relative path string), `expected_kind` ("json" | "csv" | "manifest" | "audit").

### 6.2 `malformed_json`

- **When:** a reload read a JSON file that fails to parse, or that is missing one of the §5.1 frozen top-level keys.
- **Carries:** `path` (relative path string), `reason` (string from the parser / key validator).

### 6.3 `malformed_csv`

- **When:** a reload read a CSV file that fails to parse, that is missing the §5.2 frozen header row, or whose row count is inconsistent with the JSON's `outputs` length.
- **Carries:** `path` (relative path string), `reason` (string from the parser / header validator).

### 6.4 `manifest_mismatch`

- **When:** a reload read a manifest that fails the §4.5 path-integrity check, or whose `metric_definition_version` is not `"4b-1.0.0"`.
- **Carries:** `path` (relative path string), `field` (the failing field name), `expected` (the expected value), `actual` (the actual value).

### 6.5 `canonical_payload_hash_mismatch`

- **When:** a reload recomputed `canonical_payload_hash` from the JSON's `outputs` array and the recomputed value differs from the manifest's recorded value.
- **Carries:** `path` (relative path string), `expected` (manifest value), `actual` (recomputed value).

### 6.6 `audit_payload_hash_mismatch`

- **When:** a reload recomputed `SHA-256(audit_bytes)` and the recomputed value differs from the manifest's `audit_payload_hash`.
- **Carries:** `path` (relative path string), `expected` (manifest value), `actual` (recomputed value).

### 6.7 `row_order_mismatch`

- **When:** a reload compared the CSV's `metric_name` column order against the JSON's `outputs[*].metric_name` order and the two orderings differ.
- **Carries:** `path` (relative path string), `csv_order` (list[str]), `json_order` (list[str]), `first_diverging_index` (int).

### 6.8 `metric_definition_version_mismatch`

- **When:** a reload read a JSON / manifest / audit file whose `metric_definition_version` is not `"4b-1.0.0"`. This is a hard mismatch because the 4b-1.0.0 binding is the only version this contract understands.
- **Carries:** `path` (relative path string), `expected` ("4b-1.0.0"), `actual` (the actual version string).

### 6.9 `mask_hash_mismatch`

- **When:** a reload read a JSON file whose `evaluation_mask_hash` differs from the value the caller expected. The 4c-3 reload is a typed operation: the caller specifies the `(run_id, evaluation_mask_hash)` they expect to verify, and a reload against a different mask hash is an error (not a silent fallback).
- **Carries:** `expected_mask_hash` (the caller's expected value), `actual_mask_hash` (the value in the artifact).

### 6.10 `forbidden_implicit_fallback`

- **When:** a reload operation tries to use `current` / `latest` / `most recent` / any other implicit selection against the artifact set. The 4c-3 contract forbids implicit selection at every layer; a reload MUST be invoked with an explicit `(run_id, evaluation_mask_hash)` and an explicit `output_dir` (or set of manifest paths).
- **Carries:** `attempted_selection` (the implicit selector the caller tried to use).

---

## 7. Test contract (§§7.1 – 7.7)

The 4c-3 test contract is a description of the test surface, **not** an implementation. The implementation PR (a future slice requiring separate Charles authorization) MUST cover the following test cases.

### 7.1 Production-shaped E2E happy path

- A test wires the 4c-1 service layer to a fixture materialization (per §3.1), invokes the CLI subprocess (per §3.3), and asserts:
  - CLI exit code is `0` (no `MetricBlocker` in this fixture) or `3` (fixture intentionally triggers a blocker).
  - The four files exist with the §6.1 filename pattern.
  - The four files' contents match the pre-recorded byte-level expected values (modulo audit timestamp).
  - The manifest's `canonical_payload_hash` matches the JSON's `canonical_payload_hash`.
  - The manifest's `audit_payload_hash` matches `SHA-256(audit_bytes)`.

### 7.2 Reload from manifest

- A test reads only the manifest file (not the original `compute_metrics` invocation context), reconstructs the `(run_id, evaluation_mask_hash, scope_id)` identity, and verifies the JSON / CSV / audit artifacts against the manifest (per §§4.2 – 4.5).
- The test MUST assert that the reload is stateless: invoking it twice in a row produces identical verification results.

### 7.3 JSON / CSV consistency check

- A test reads the JSON file and the CSV file (without consulting the manifest) and asserts the §4.4 row-consistency invariant. The test MUST assert the failure surface is `row_order_mismatch` (§6.7) when the CSV's row order is scrambled.

### 7.4 Audit hash check

- A test recomputes `SHA-256(audit_bytes)` and asserts it matches the manifest's `audit_payload_hash`. The test MUST assert the failure surface is `audit_payload_hash_mismatch` (§6.6) when the audit file is corrupted post-write.

### 7.5 Deterministic re-run check

- A test invokes the E2E happy path twice with the same fixture and asserts the four files (excluding the audit file's timestamp-bearing fields) are byte-identical. The test MUST assert the failure surface is `canonical_payload_hash_mismatch` (§6.5) when the JSON's `outputs` array is modified between the two runs.

### 7.6 Negative tests for corrupted artifact / hash / path

- The test contract MUST cover at least one negative test per failure kind in §6:
  - `missing_artifact` — delete a file post-write and reload.
  - `malformed_json` — write a syntactically invalid JSON file and reload.
  - `malformed_csv` — write a CSV file with a missing header column and reload.
  - `manifest_mismatch` — modify the manifest's `metric_definition_version` post-write and reload.
  - `canonical_payload_hash_mismatch` — modify a single byte in the JSON's `outputs` array post-write and reload.
  - `audit_payload_hash_mismatch` — modify a single byte in the audit file post-write and reload.
  - `row_order_mismatch` — swap two rows in the CSV post-write and reload.
  - `metric_definition_version_mismatch` — write a JSON file with `metric_definition_version = "4b-0.9.0"` and reload.
  - `mask_hash_mismatch` — pass an `expected_mask_hash` different from the JSON's and reload.
  - `forbidden_implicit_fallback` — assert that no test path or public API exposes an implicit selector.

### 7.7 No database / network side channel

- The 4c-3 implementation MUST NOT introduce database IO or network IO beyond the fixture / provider boundary explicitly authorized by §3.1.
- The test contract MUST include a test that asserts no SQL query, no HTTP request, no file IO outside the authorized boundary is performed during a 4c-3 reload (e.g. via a `monkeypatch` of `urllib.request` / `requests.*` / `backend.app.db.session` and an assertion that no patched call was made).

---

## 8. Implementation split (§§8.1 – 8.3)

### 8.1 Design amendment only in this PR

- This PR (`codex/task-011-phase4c-3-design-amendment`) is design-only. It freezes the 4c-3 contract. It does not implement 4c-3 code, modify 4c-3 tests, or create migrations.

### 8.2 Future implementation must require separate Charles authorization

- Any future PR that adds 4c-3 implementation code, modifies 4c-3 tests, or creates migrations MUST be authorized separately by Charles. The authorization MUST be explicit, per-slice, and NOT assumed from a "design freeze" or "ready" signal on the design PR.
- The future implementation PR MUST be opened as a Draft and MUST remain Draft until Charles explicitly authorizes freeze + Ready.
- The future implementation PR MUST bind to a fresh base from main taken at the time of the future authorization, NOT to this design PR's head (this design PR will be merged to main separately, and the future implementation PR will be rebased on top of that merge).

### 8.3 Future implementation must use a separate Draft PR

- The future 4c-3 implementation MUST be a separate Draft PR. It MUST NOT be appended to this design PR.
- The future implementation PR MUST preserve the Phase 4c / 4c-1 / 4c-2 frozen contract; any contract change requires a new design amendment PR (with full governance cycle), not a code-level change in the implementation PR.

---

## 9. Frozen authority (§§9.1 – 9.3)

### 9.1 PR binding

- This design amendment binds to:
  - **PR #41** (Phase 4c design amendment, MERGED)
  - **PR #42** (Phase 4c-1 service layer implementation, MERGED)
  - **PR #44** (Phase 4c-2 CLI + deterministic export implementation, MERGED)
  - **PR #44 merge commit**: `a3a65e9097dca886d655c3e52e1c0234d606d9fd`

### 9.2 Content SHA preservation

- The following content SHAs MUST be preserved unchanged on main:
  - **Phase 4c design amendment content SHA**: `9f1f541367ee7c4ea3814f0068f682b29e590758690dcb2098cadd5de7796216`
  - **Phase 4b design amendment content SHA**: `7ed7cb567c72f107b4a83ed64f0ed66309fdd98049110afa4ec3831598e7c63a`
  - **Phase 4a design amendment content SHA**: `632e2e1f2880c9a6d7b87ee9f90565223ece69aaee43bea620f526c1fe1c8f3c`
- This design amendment does NOT rotate any of the above content SHAs.

### 9.3 Issue / PR invariants

- Issue #43 (Phase 4c-2 tracking) MUST remain CLOSED / COMPLETED. It MUST NOT be reopened.
- Issue #21 / #33 / #36 / #38 MUST remain in their current CLOSED / COMPLETED state.
- Issue #23 / PR #24 (infra track) MUST remain in their current state (Issue #23 OPEN; PR #24 CLOSED / draft / not merged). 4c-3 MUST NOT modify either.
- Branch `codex/task-011-phase4c-2-cli-export` MUST NOT be deleted by 4c-3.

---

## 10. Test contract (per §7) summary table

| § | Test case | Failure kind asserted |
| - | --- | --- |
| 7.1 | Production-shaped E2E happy path | (success) |
| 7.2 | Reload from manifest | (success) |
| 7.3 | JSON / CSV consistency check | `row_order_mismatch` |
| 7.4 | Audit hash check | `audit_payload_hash_mismatch` |
| 7.5 | Deterministic re-run check | `canonical_payload_hash_mismatch` |
| 7.6a | Missing artifact | `missing_artifact` |
| 7.6b | Malformed JSON | `malformed_json` |
| 7.6c | Malformed CSV | `malformed_csv` |
| 7.6d | Manifest mismatch | `manifest_mismatch` |
| 7.6e | JSON byte-corrupted | `canonical_payload_hash_mismatch` |
| 7.6f | Audit byte-corrupted | `audit_payload_hash_mismatch` |
| 7.6g | CSV row order scrambled | `row_order_mismatch` |
| 7.6h | Wrong metric definition version | `metric_definition_version_mismatch` |
| 7.6i | Wrong mask hash | `mask_hash_mismatch` |
| 7.6j | Implicit fallback attempt | `forbidden_implicit_fallback` |
| 7.7 | No DB / network side channel | (no patched call observed) |

---

## 11. Open questions (deferred to design review)

- **OQ1.** Should 4c-3 introduce a new CLI subcommand (e.g. `verify`) or expose a Python function only? The current design is function-first; a CLI surface is a future option.
- **OQ2.** Should the 4c-3 failure kinds (§6) live in `backend/app/rolling_backtest/service.py` (alongside the 4c-1 `ServiceContractError`) or in a new module (e.g. `backend/app/rolling_backtest/verify.py`)? The implementation PR will bind this decision.
- **OQ3.** Should the byte-level snapshot fixture (§3.5) live in the repo as committed JSON, or generated on the fly from a known-seed random source? The implementation PR will bind this decision.
- **OQ4.** How does 4c-3 interact with the audit file's timestamp fields? The current design exempts the audit file from byte-comparison (§4.6) and verifies it via `audit_payload_hash` instead. An alternative is to allow the audit file to be ignored entirely for byte-comparison purposes. The implementation PR will bind this decision.

---

## 12. References

- Phase 4a design amendment: `docs/task-11-phase4a-evaluation-mask-amendment.md` (content SHA `632e2e1f2880c9a6d7b87ee9f90565223ece69aaee43bea620f526c1fe1c8f3c`)
- Phase 4b design amendment: `docs/task-11-phase4b-metric-formulas-amendment.md` (content SHA `7ed7cb567c72f107b4a83ed64f0ed66309fdd98049110afa4ec3831598e7c63a`)
- Phase 4c design amendment: `docs/task-11-phase4c-service-cli-export-amendment.md` (content SHA `9f1f541367ee7c4ea3814f0068f682b29e590758690dcb2098cadd5de7796216`)
- 4c-1 service layer: PR #42 (MERGED) → `backend/app/rolling_backtest/service.py` on main
- 4c-2 CLI + export: PR #44 (MERGED) → `backend/app/rolling_backtest/cli.py` + `backend/app/rolling_backtest/export.py` on main
- 4c-2 merge commit: `a3a65e9097dca886d655c3e52e1c0234d606d9fd`
- 4c-2 closeout comment: `#4895013757` on Issue #43

---

> **End of design amendment. No implementation. No tests. No migrations. No production code. PR remains Draft until Charles's separate freeze + Ready authorization.**
