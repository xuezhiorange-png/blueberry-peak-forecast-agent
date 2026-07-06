# TASK-011 Phase 4c — Design Amendment: Service Layer, CLI, and Deterministic Export

> **Status:** Design-only. **Not** implementation. **Not** migration. **Not** tests. **Not** production code.
> **This PR does NOT implement code, modify tests, or create migrations.** Phase 4c depends on Phase 4a + Phase 4b as frozen design inputs.
>
> **Implementation split (binding for this amendment):**
> - **4c-1** — public service layer function contract only.
> - **4c-2** — CLI command contract + deterministic JSON / CSV / manifest export schema.
> - **4c-3** — production-shaped E2E / reload integrity (NOT in scope for this amendment; reserved for a later design slice that consumes 4c-1 + 4c-2 outputs).
>
> **This document freezes 4c-1 + 4c-2 contracts only.** 4c-3 is mentioned only to mark its boundary; its contract will be authored as a follow-up amendment PR after 4c-1 + 4c-2 land.

---

## 0. Header / Status

- **Phase 4c is design-only.** It freezes contracts for the public service layer, the CLI surface, and the deterministic export payload schema. Implementation is NOT authorized.
- **This PR does NOT implement code.** No source file under `backend/app/rolling_backtest/` is touched.
- **This PR does NOT modify tests.** No new test file is added.
- **This PR does NOT create migrations.** No Alembic revision is added.
- **This PR does NOT create CLI code, API code, or frontend code.** Those are 4c-1 / 4c-2 *contract* targets only.
- **Phase 4c depends on Phase 4a (frozen) + Phase 4b (frozen) as design inputs.**
- Phase 4c planning Issue: #38 (canonical, OPEN).
- Issue #21 (TASK-011 umbrella) must remain OPEN for this PR to proceed.
- Issue #33 (Phase 4 planning) must remain OPEN for this PR to proceed.
- Issue #36 (Phase 4b planning, CLOSED / COMPLETED) must remain CLOSED for this PR to proceed.
- PR must remain **Draft** until Charles explicitly authorizes freeze + Ready.

---

## 1. Dependency anchors

Phase 4c consumes these frozen upstream outputs:

- **main SHA**: `18d3043d4e03ada82f89f2448222afbfbca1e874`
- **PR #40 merge commit**: `18d3043d4e03ada82f89f2448222afbfbca1e874` (Phase 4b implementation, MERGED 2026-07-06T09:51:31Z)
- **PR #40 head SHA**: `35f594a6bfdfd32230a2fa9b2d722a97aa120588`
- **Phase 4a Design Amendment Content SHA**: `632e2e1f2880c9a6d7b87ee9f90565223ece69aaee43bea620f526c1fe1c8f3c`
- **Phase 4a docs**: `docs/task-11-phase4a-evaluation-mask-amendment.md`
- **Phase 4a Frozen Authority Base SHA**: `7340ec51865645a2c06b2d2e1e54d24cd457c831` (preserved, not rotated)
- **Phase 4a Frozen Amendment Content SHA**: `f2896ae475d4e007fb2e54ad07f294e718d1e171` (preserved, not rotated)
- **Phase 4a Design Amendment byte count**: 17,824
- **Phase 4a freeze comment (on PR #35)**: `#4889240526`
- **Issue #34 canonical closeout comment**: `#4889491442`
- **Phase 4b Design Amendment Content SHA**: `7ed7cb567c72f107b4a83ed64f0ed66309fdd98049110afa4ec3831598e7c63a`
- **Phase 4b docs**: `docs/task-11-phase4b-metric-formulas-amendment.md`
- **Phase 4b Design Amendment byte count**: 18,000
- **Phase 4b freeze comment (on PR #37)**: `#4889788635`
- **Phase 4b freeze comment body_length**: 3,856
- **Phase 4b PR #37 merge commit**: `6b59092933205ba4b0e37f3539c8eaca2a506246`
- **Phase 4b implementation PR #40 merge commit**: `18d3043d4e03ada82f89f2448222afbfbca1e874`
- **Phase 4b post-merge main CI**: Run `28782980116`, completed / success
- **Phase 4b metric definition version**: `4b-1.0.0` (frozen at `backend/app/rolling_backtest/metrics.py`)
- **Phase 4b default decimal scale**: 6
- **Phase 4b empty mask hash**: 64 lowercase hex zeroes
- **Issue #21**: TASK-011 umbrella, OPEN
- **Issue #33**: Phase 4 planning, OPEN
- **Issue #36**: Phase 4b planning, CLOSED / COMPLETED
- **Issue #38**: Phase 4c planning, OPEN
- **Refs:**
  - Issue #21 — TASK-011 umbrella, OPEN
  - Issue #29 — Phase 3.1, CLOSED / COMPLETED
  - Issue #33 — Phase 4 planning, OPEN
  - Issue #34 — Phase 4a design planning, CLOSED / COMPLETED
  - Issue #36 — Phase 4b planning, CLOSED / COMPLETED
  - Issue #38 — Phase 4c planning, OPEN
  - PR #30 — Phase 3.1 implementation, MERGED
  - PR #35 — Phase 4a design amendment, MERGED
  - PR #37 — Phase 4b design amendment, MERGED
  - PR #40 — Phase 4b implementation, MERGED

---

## 2. Phase 4c scope boundary

### 2.1 In scope (4c-1 + 4c-2 contract freeze)

- Public service-layer function signature contract — the public entry point that downstream callers (CLI in 4c-2, API in a future unrelated slice) invoke to compute Phase 4b metrics over a Phase 4a materialized evaluation row set.
- Service-layer parameter contract — typed inputs (run id, scope, evaluation mask binding, optional metric subset) and typed outputs (`EvaluationResult` payload + canonical payload hash from Phase 4b).
- Service-layer error / blocker propagation contract — how Phase 4b `MetricBlocker` entries surface to service callers; no silent fallbacks.
- CLI command surface — flag grammar, required vs optional flags, exit code model.
- CLI argument validation contract — including `--mask-hash` hex format check, `--output-dir` writability check, `--scope` JSON parse check.
- Deterministic JSON export schema — sorted keys, Decimal canonical, no native float.
- Deterministic CSV export schema — column ordering, header row determinism, row ordering, escaping rules.
- Manifest export schema — covers inputs consumed, outputs produced, mask binding, metric definition version, run id, scope identity, canonical payload hash.
- Output path and filename determinism — exact filename template; behavior on overwrite vs collision.
- Idempotency policy — repeated invocations with identical inputs produce byte-identical outputs (or refuse with a structured error, never silently merge).
- Audit / provenance payload — every CLI run and service call emits a deterministic audit record bound to the same Phase 4b canonical payload hash.
- Error / blocker model for service + CLI — the contract for how MetricBlocker, invalid input, and IO errors surface.
- Test contract for 4c-1 + 4c-2 (NOT implementation in this PR).

### 2.2 Out of scope (binding for any 4c-1 / 4c-2 / 4c-3 implementation)

- Phase 4a materialization redefinition (already complete and frozen; do not touch).
- Phase 4b metric formula redefinition (already merged; do not touch).
- Task 8 / Task 9 / Task 10 semantic changes.
- Task 10 `replay_trained_model` (explicitly deferred to a later independent design decision).
- Model training changes.
- Database migrations (Alembic revisions) — unless a separately authorized schema-gap amendment explicitly opens that scope.
- API endpoint implementation — `backend/app/api/` must not be touched by 4c-1 / 4c-2 / 4c-3.
- Frontend work — `frontend/` (if present) must not be touched.
- Production-shaped scheduling, drift monitoring, alerting, cron / systemd / k8s wiring.
- Any "current" / "latest" / "most recent" implicit selection — Phase 4c always takes an explicit run id, scope, and mask binding. No implicit fallback.
- 4c-3 production-shaped E2E / reload integrity contract — referenced only as a future boundary; this amendment does NOT freeze it.
- 4c-1 / 4c-2 implementation code (this PR is design-only).
- 4c-1 / 4c-2 implementation tests (this PR is design-only).
- Closeout PR for TASK-011.
- Branch deletion.
- Issue state changes — Issue #21 / #33 / #36 / #38 must remain as specified in §1.

---

## 3. Public service layer function contract (4c-1)

The public service layer is a thin façade over Phase 4b metric primitives. It does NOT recompute metrics; it reads Phase 4a materialization, passes the row set to Phase 4b `evaluate_scope` / `split_by_factory`, and returns the typed payload.

### 3.1 Module

- **Path (binding for 4c-1 implementation, NOT in this PR):** `backend/app/rolling_backtest/service.py`
- **Exported from:** `backend/app/rolling_backtest/__init__.py` (minimum-extension rule applies, no other module touched)

### 3.2 Function signature (frozen)

```python
def compute_metrics(
    *,
    run_id: str,
    scope: Mapping[str, Any],
    mask_hash: str,
    metric_subset: tuple[str, ...] | None = None,
    decimal_scale: int = DEFAULT_DECIMAL_SCALE,
) -> EvaluationResult:
    """Public service-layer entry point. Pure: no IO, no side effects.
    Reads Phase 4a materialization by (run_id, mask_hash); computes the
    Phase 4b metric subset; returns a typed EvaluationResult carrying
    the canonical payload hash.

    Parameters
    ----------
    run_id : str
        Stable Phase 4a logical run identifier. REQUIRED. Must match a
        materialized Phase 4a run; no implicit selection.
    scope : Mapping[str, Any]
        Scope identity (run/node/horizon/farm/variety/model_version/eval_mask_hash).
        Must include ``node``. Mirrors the Phase 4b ``scope`` contract.
    mask_hash : str
        64-char lowercase hex Phase 4a evaluation mask hash. Validated
        against the same regex as Phase 4b ``EvaluationMaskState``.
    metric_subset : tuple[str, ...] | None
        Optional explicit allowlist of metric names. ``None`` ⇒ run the
        full Phase 4b metric set. Names not in the Phase 4b public
        surface raise ``ServiceContractError``.
    decimal_scale : int
        Defaults to ``DEFAULT_DECIMAL_SCALE`` (6). Must be ≥ 0.

    Returns
    -------
    EvaluationResult
        Phase 4b typed result with ``canonical_payload_hash``. The
        payload is byte-stable for identical inputs.

    Raises
    ------
    ServiceContractError
        On invalid ``mask_hash``, unknown ``metric_subset`` name,
        missing Phase 4a materialization for ``run_id``, or
        ``decimal_scale < 0``.
    """
```

### 3.3 Side-effect contract (frozen)

- `compute_metrics` MUST NOT write to disk, the database, or any other side channel.
- `compute_metrics` MUST NOT make network calls.
- `compute_metrics` MUST be re-entrant (safe to call from concurrent threads; no module-level mutable state).
- `compute_metrics` MUST be deterministic: identical inputs (run_id, scope, mask_hash, metric_subset, decimal_scale) MUST produce byte-identical `EvaluationResult.canonical_payload_hash` (delegated to Phase 4b).

### 3.4 Service-layer error / blocker model (4c-1)

| Condition | Behavior |
|---|---|
| `mask_hash` not 64-char lowercase hex | Raise `ServiceContractError(kind="invalid_mask_hash", ...)` |
| `run_id` not found in Phase 4a materialization | Raise `ServiceContractError(kind="missing_run", ...)` |
| `mask_hash` not bound to the named `run_id` | Raise `ServiceContractError(kind="mask_hash_unbound", ...)` |
| `metric_subset` contains a name not in the Phase 4b public surface | Raise `ServiceContractError(kind="unknown_metric", metric=...)` |
| `scope` missing `node` | Raise `ServiceContractError(kind="invalid_scope", ...)` |
| `decimal_scale < 0` | Raise `ServiceContractError(kind="invalid_decimal_scale", ...)` |
| Phase 4b returns a `MetricBlocker` (zero-denominator, etc.) | Surface in `EvaluationResult.outputs[*].blocked_reasons` — DO NOT raise; the caller inspects blockers via the standard Phase 4b audit payload |

`ServiceContractError` is a subclass of `ValueError` for forward-compat. 4c-1 defines the error *contract*; the actual class lives in the 4c-1 implementation PR (not this amendment).

---

## 4. CLI command contract (4c-2)

The CLI is a thin wrapper around `compute_metrics` plus the deterministic export writer. It does NOT compute metrics; it does NOT bypass `compute_metrics` validation.

### 4.1 Module / entry point

- **CLI module path (binding for 4c-2 implementation, NOT in this PR):** `backend/app/rolling_backtest/cli.py`
- **Entry point name (binding):** `python -m backend.app.rolling_backtest.cli`
- **Subcommand (binding):** `compute-metrics` (first subcommand; future subcommands will be additive and not break the existing flag grammar)

### 4.2 Flag grammar (frozen)

```
python -m backend.app.rolling_backtest.cli compute-metrics \
    --run-id <str> \
    --scope <json> \
    --mask-hash <64-char-lowercase-hex> \
    --output-dir <absolute-path> \
    [--metric-subset <name>[,<name>,...]] \
    [--decimal-scale <int>] \
    [--overwrite <never|missing|always>] \
    [--no-audit] \
    [--quiet]
```

| Flag | Required | Default | Notes |
|---|---|---|---|
| `--run-id` | yes | — | Phase 4a logical run id |
| `--scope` | yes | — | JSON object; MUST include `node` |
| `--mask-hash` | yes | — | 64-char lowercase hex |
| `--output-dir` | yes | — | Absolute path; must be writable |
| `--metric-subset` | no | full Phase 4b set | Comma-separated allowlist |
| `--decimal-scale` | no | 6 | Must be ≥ 0 |
| `--overwrite` | no | `missing` | `never` / `missing` / `always` |
| `--no-audit` | no | audit ON | Skip audit-record emission |
| `--quiet` | no | stderr logging ON | Suppress stderr progress logs |

### 4.3 Exit code model (frozen)

| Exit code | Meaning |
|---|---|
| 0 | Success; outputs written; canonical payload hash on stdout (unless `--quiet`) |
| 2 | `ServiceContractError` raised (invalid input, missing run, etc.) |
| 3 | Phase 4b produced a `MetricBlocker` (the caller's signal that the metric value is not defined; output files are still written with the blocker audit) |
| 4 | IO error writing the export directory |
| 5 | Hash collision on `--overwrite=never` |
| 64 | CLI usage error (missing required flag, malformed JSON in `--scope`, etc.) — uses `argparse` standard |

### 4.4 CLI audit contract (4c-2)

- Every successful CLI run writes one audit JSON file: `<output-dir>/audit/<run-id>__<scope-id>__<canonical_payload_hash>.json`
- Audit JSON MUST contain: `cli_version`, `command_invocations` (argv list), `inputs` (run_id, scope, mask_hash, metric_subset, decimal_scale, overwrite_policy), `outputs` (file paths + their own SHA-256), `metric_definition_version` (mirror of Phase 4b `4b-1.0.0`), `evaluation_mask_hash`, `run_id`, `started_at_utc`, `finished_at_utc`, `exit_code`.
- Audit file is itself canonicalized via `canonical_payload_hash`.
- `--no-audit` skips the audit file (caller responsibility).

### 4.5 CLI error / blocker model (4c-2)

- All `ServiceContractError` (4c-1) surface as exit code 2 with a single-line stderr message + machine-readable JSON on stdout (key: `error`, value: `{kind, message, scope_id, metric_definition_version, evaluation_mask_hash}`).
- `MetricBlocker` from Phase 4b surfaces as exit code 3, with the blocker list mirrored in stdout JSON.
- IO errors surface as exit code 4.
- Hash collision on `--overwrite=never` surfaces as exit code 5 with the conflicting file path on stderr.

---

## 5. Deterministic export schema (4c-2)

### 5.1 JSON export

- **File name (frozen):** `<output-dir>/json/<run-id>__<scope-id>__<canonical_payload_hash>.json`
- **Encoding:** UTF-8, no BOM.
- **Format:** canonical JSON serialization (RFC 8785-style: sorted keys at every object level, no whitespace, no trailing newline).
- **Top-level keys (frozen order, lexicographic):**
  - `canonical_payload_hash` (string)
  - `cli_invocation` (object — only when written by CLI; absent when written by service-layer test or programmatic call)
  - `decimal_scale` (integer)
  - `evaluation_mask_hash` (string)
  - `metric_definition_version` (string — must be `4b-1.0.0` for this round)
  - `outputs` (array — `MetricOutput.to_audit_payload()`)
  - `run_id` (string)
  - `scope_id` (string)
  - `written_at_utc` (string — ISO 8601 with `Z` suffix)
- **Decimal rendering:** canonical string form (e.g. `"0.010000"`), no `E` notation, no leading `+`, no leading zeros for non-zero values, `-0` not allowed.
- **Float rule:** `float` MUST NOT appear in the payload. `Decimal` only.
- **Null / missing rule:** explicit `null` for null fields; missing keys are not used.

### 5.2 CSV export

- **File name (frozen):** `<output-dir>/csv/<run-id>__<scope-id>__<canonical_payload_hash>.csv`
- **Encoding:** UTF-8, no BOM.
- **Line terminator:** `\n` (LF only; no `\r\n`).
- **Header row (frozen order):** `metric_name,metric_value,comparable_row_count,decimal_scale,evaluation_mask_hash,metric_scope_identity,metric_definition_version,blocker_count,blocker_kinds`
- **Row ordering:** same as the JSON `outputs` array (i.e. canonical Phase 4b order — counters first, then aggregate metrics, in the order emitted by `evaluate_scope`).
- **Decimal rendering:** same rule as JSON.
- **Escaping:** standard CSV (RFC 4180) — fields containing `,`, `"`, or newline are wrapped in `"…"` with internal `"` doubled.
- **Trailing newline:** required.

### 5.3 Manifest export

- **File name (frozen):** `<output-dir>/manifest/<run-id>__<scope-id>__<canonical_payload_hash>.json`
- **Top-level keys (frozen order, lexicographic):**
  - `audit_payload_hash` (string — SHA-256 of the audit file bytes, only present if audit was emitted)
  - `canonical_payload_hash` (string)
  - `csv_path` (string — relative to `output_dir`)
  - `decimal_scale` (integer)
  - `evaluation_mask_hash` (string)
  - `inputs` (object — `metric_subset`, `overwrite_policy`, `run_id`, `scope`)
  - `json_path` (string — relative to `output_dir`)
  - `metric_definition_version` (string — must be `4b-1.0.0`)
  - `scope_id` (string)
  - `written_at_utc` (string)
- The manifest is the index file. It is the only file that callers must read first; the JSON and CSV paths in it are guaranteed to exist (or the manifest itself was never written).

### 5.4 Output directory layout (frozen)

```
<output-dir>/
├── audit/
│   └── <run-id>__<scope-id>__<canonical_payload_hash>.json
├── csv/
│   └── <run-id>__<scope-id>__<canonical_payload_hash>.csv
├── json/
│   └── <run-id>__<scope-id>__<canonical_payload_hash>.json
└── manifest/
    └── <run-id>__<scope-id>__<canonical_payload_hash>.json
```

- All four sub-directories are required and are created by the writer if missing.
- Filename collision policy: see §6.

---

## 6. Output path and filename determinism + overwrite / collision policy

### 6.1 Path determinism

- Given the same `(run_id, scope_id, canonical_payload_hash, output_dir)`, the writer MUST always produce the same four file paths.
- `scope_id` is the Phase 4b `metric_scope_identity` hex string (not the human-readable scope object). The writer derives `scope_id` from the Phase 4b result; it does not re-derive it from the caller's `scope` object to avoid divergence.
- `canonical_payload_hash` is the Phase 4b `EvaluationResult.canonical_payload_hash` hex string.

### 6.2 Overwrite policy (`--overwrite` flag)

| Value | Behavior on pre-existing file |
|---|---|
| `never` | Exit code 5 (`HASH_COLLISION`) if any of the four target file paths already exists. The file system is NOT modified. |
| `missing` (default) | Write only if the target file path does NOT exist. If it already exists, exit code 5. |
| `always` | Overwrite. The previous file bytes are replaced byte-for-byte with the new content. The audit record MUST record both `previous_canonical_payload_hash` (if available from the existing audit file) and the new one. |

- `--overwrite=always` is for iterative development; CI / production runs SHOULD use `never` or `missing` to surface drift.
- The four target paths are checked and written atomically (write to `<path>.tmp.<random>`, then `os.replace(...)`); a crash mid-write leaves a `.tmp` file the next run can detect and remove (see §6.3).

### 6.3 Crash-recovery (deterministic)

- On startup, the writer scans `output_dir` for `*.tmp.<random>` files older than 1 hour (configurable; default 3600s) and removes them.
- A `*.tmp.<random>` file younger than the threshold is left alone (concurrent writer).

---

## 7. Audit / provenance payload

### 7.1 CLI audit file (4c-2 §4.4)

- The audit JSON is byte-stable for identical inputs + clock — but the `started_at_utc` / `finished_at_utc` fields make the file NOT byte-stable across invocations. The `audit_payload_hash` is therefore recorded in the manifest to allow byte-stable references at the manifest level.

### 7.2 Service-layer audit (4c-1)

- `compute_metrics` does NOT write an audit file (it is pure, no IO).
- The Phase 4b `EvaluationResult.canonical_payload_hash` IS the service-layer audit binding: any caller that wants to record a service-layer invocation records the hash + the input tuple (run_id, scope, mask_hash, metric_subset, decimal_scale).
- 4c-1 does NOT define a new audit format; it reuses Phase 4b's.

### 7.3 Provenance chain (binding)

The full provenance chain for any 4c-2 export is:

1. Phase 4a `evaluation_mask_hash` (frozen in design).
2. Phase 4b `metric_definition_version` (frozen: `4b-1.0.0`).
3. Phase 4b `canonical_payload_hash` (computed by `evaluate_scope`).
4. 4c-2 manifest `canonical_payload_hash` (mirrors Phase 4b).
5. 4c-2 audit `audit_payload_hash` (SHA-256 of audit bytes; bound to 4c-2 CLI version).

A consumer that wants to verify "this CSV is the metric output for run X, scope Y, mask Z, metric definition 4b-1.0.0" reads the manifest, verifies the manifest's `canonical_payload_hash` matches the embedded `csv_path` JSON's `canonical_payload_hash`, and re-derives the CSV content from the JSON. No alternative code path.

---

## 8. Idempotency and overwrite / collision policy

(Summary — see §6.2 for the table; this section captures the binding rules.)

- **Idempotency (service layer):** `compute_metrics(...)` is pure; repeated calls with identical inputs return byte-identical `EvaluationResult` (delegated to Phase 4b). Service layer is idempotent by construction.
- **Idempotency (CLI):** A CLI run with identical `(run_id, scope, mask_hash, metric_subset, decimal_scale, overwrite_policy)` and identical `output_dir` produces a deterministic outcome:
  - `overwrite=never` or `missing`: first run writes; second run exits 5 (`HASH_COLLISION`).
  - `overwrite=always`: every run rewrites; the four target files are byte-identical to the first run (modulo audit timestamps).
- **Collision policy:** Collision is defined as "any of the four target paths already exists". It is NOT a hash collision; it is a path collision. The CLI refuses rather than silently overwriting unless `--overwrite=always` is passed.
- **Concurrent writers:** The writer uses `<path>.tmp.<random>` + `os.replace()` for atomicity. Two concurrent writers targeting the same paths will each write their own `.tmp` file, then race on `os.replace`. The loser's `os.replace` overwrites the winner's. The audit file records the actual final state; downstream consumers re-derive the canonical hash from the JSON, not from the audit.

---

## 9. Error / blocker model (consolidated)

| Layer | Condition | Behavior |
|---|---|---|
| Service (4c-1) | `mask_hash` not 64-char lowercase hex | Raise `ServiceContractError(kind="invalid_mask_hash", ...)` |
| Service (4c-1) | `run_id` not found | Raise `ServiceContractError(kind="missing_run", ...)` |
| Service (4c-1) | `mask_hash` not bound to `run_id` | Raise `ServiceContractError(kind="mask_hash_unbound", ...)` |
| Service (4c-1) | `metric_subset` contains unknown name | Raise `ServiceContractError(kind="unknown_metric", metric=...)` |
| Service (4c-1) | `scope` missing `node` | Raise `ServiceContractError(kind="invalid_scope", ...)` |
| Service (4c-1) | `decimal_scale < 0` | Raise `ServiceContractError(kind="invalid_decimal_scale", ...)` |
| Service (4c-1) | Phase 4b returns `MetricBlocker` | Surface via `EvaluationResult.outputs[*].blocked_reasons` (do NOT raise) |
| CLI (4c-2) | `ServiceContractError` from 4c-1 | Exit 2 + JSON `{error: {kind, message, ...}}` on stdout |
| CLI (4c-2) | Phase 4b `MetricBlocker` | Exit 3 + blocker list on stdout (outputs still written) |
| CLI (4c-2) | `argparse` failure | Exit 64 (standard) |
| CLI (4c-2) | IO error writing export | Exit 4 |
| CLI (4c-2) | Path collision on `overwrite=never/missing` | Exit 5 + conflicting path on stderr |
| CLI (4c-2) | Audit emission failure (when audit ON) | Exit 4 (atomic: manifest only written if audit succeeds) |

All errors carry `metric_definition_version` and `evaluation_mask_hash` in the JSON payload so downstream tooling can correlate.

---

## 10. Test contract (4c-1 + 4c-2)

This section is the test *contract* — NOT the tests. Tests land in the 4c-1 / 4c-2 implementation PRs.

### 10.1 Service-layer tests (4c-1)

- `compute_metrics` returns identical `canonical_payload_hash` for identical inputs across 1000 calls.
- `compute_metrics` raises `ServiceContractError(kind="invalid_mask_hash")` for a 63-char or 65-char hex string.
- `compute_metrics` raises `ServiceContractError(kind="missing_run")` for a `run_id` not in the materialized Phase 4a set.
- `compute_metrics` raises `ServiceContractError(kind="mask_hash_unbound")` when `mask_hash` is valid hex but does not bind to the named `run_id`.
- `compute_metrics(metric_subset=("mean_absolute_error",))` returns an `EvaluationResult` whose `outputs` list contains exactly the named metric plus the four counters (row_count, comparable_row_count, masked_row_count, withheld_row_count).
- `compute_metrics(metric_subset=("not_a_real_metric",))` raises `ServiceContractError(kind="unknown_metric", metric="not_a_real_metric")`.
- `compute_metrics(scope={})` (missing `node`) raises `ServiceContractError(kind="invalid_scope")`.
- `compute_metrics(decimal_scale=-1)` raises `ServiceContractError(kind="invalid_decimal_scale")`.
- Phase 4b `MetricBlocker` entries surface in `EvaluationResult.outputs[*].blocked_reasons` and the function returns normally (no raise).
- Re-entrancy: 8 concurrent threads, 100 calls each, all return the same `canonical_payload_hash`.

### 10.2 CLI tests (4c-2)

- `compute-metrics --run-id X --scope {...} --mask-hash <hex> --output-dir /tmp/foo` exits 0 on success; the four files appear under `/tmp/foo/{json,csv,manifest,audit}/` with the frozen filename pattern.
- Missing `--run-id` exits 64 (argparse).
- Malformed JSON in `--scope` exits 64.
- `--mask-hash` not 64-char lowercase hex exits 64.
- `--overwrite=never` with a pre-existing target file exits 5 and the file is unmodified.
- `--overwrite=missing` (default) with a pre-existing target file exits 5.
- `--overwrite=always` with a pre-existing target file exits 0 and the file bytes match the new content exactly.
- Two consecutive runs with identical inputs + `overwrite=never` produce identical file bytes (the writer is deterministic).
- Audit file is written with the frozen key set; its `audit_payload_hash` matches the SHA-256 of the audit file bytes.
- Manifest `canonical_payload_hash` matches the Phase 4b `EvaluationResult.canonical_payload_hash` returned by `compute_metrics` for the same inputs.
- `--metric-subset mean_absolute_error,cumulative_relative_error` produces JSON / CSV / manifest whose `outputs` list contains only those two metrics plus the four counters.
- `--no-audit` suppresses the audit file; the manifest still records `audit_payload_hash: null`.
- Crash recovery: pre-existing `*.tmp.<random>` files older than the threshold are removed on startup; younger `.tmp` files are left alone.
- Post-merge: PostgreSQL parity test — running 4c-2 CLI on a materialized Phase 4a set must produce the same `canonical_payload_hash` as a re-read of the corresponding Phase 4b `EvaluationResult`.

### 10.3 CI shard impact

- 4c-1 / 4c-2 tests will be added to the existing `ci` shard per the `ci-shard-manifest.yml` carve-out. The carve-out MUST be applied in the implementation PR, not in this design amendment.
- This design PR does NOT modify `ci-shard-manifest.yml`.

---

## 11. Implementation split (binding)

| Slice | Scope | In this amendment? |
|---|---|---|
| **4c-1** | Public service layer function contract only (`service.py` + minimum `__init__.py` export) | Contract frozen in this PR (no code) |
| **4c-2** | CLI + deterministic JSON / CSV / manifest export (`cli.py` + writer modules) | Contract frozen in this PR (no code) |
| **4c-3** | Production-shaped E2E / reload integrity | NOT in this amendment; reserved for a later design slice that consumes 4c-1 + 4c-2 outputs |

Each implementation slice is a separate Draft PR with its own implementation + tests + ci-shard manifest registration. None of them lands in this amendment.

---

## 12. Forbidden scope (binding)

- **No Task 8 / 9 / 10 semantic change.** Phase 4a / 4b / 4c consume but do not modify Task 8/9/10 outputs.
- **No `replay_trained_model`** unless separately authorized in a later amendment. Phase 4c reads the materialized Phase 4a row set; it does not invoke Task 10.
- **No frontend / API** unless separately authorized. 4c-1 is a Python function; 4c-2 is a CLI; neither exposes HTTP / WS / GraphQL.
- **No production scheduling / drift monitoring / alerting.** 4c-1 / 4c-2 are on-demand; cron / systemd / k8s wiring is reserved for 4c-3 (and even 4c-3 will require a separate authorization).
- **No "current" / "latest" / "most recent" implicit fallback.** Every 4c-1 / 4c-2 call takes an explicit `run_id`, `scope`, and `mask_hash`. No silent selection of the most recent run.
- **No migrations** unless a separately authorized schema-gap amendment explicitly opens that scope. 4c-1 / 4c-2 are read-only over Phase 4a materialization.

---

## 13. Stop conditions

Work on this amendment (and any 4c-1 / 4c-2 / 4c-3 implementation derived from it) must halt and return to planning if any of the following are detected:

- Implementation code is introduced in this design PR (i.e. `service.py` or `cli.py` or any other `backend/app/rolling_backtest/*.py` file is modified by this PR).
- Tests are introduced in this design PR.
- Migrations are created.
- Phase 4a frozen semantics are changed.
- Phase 4b frozen semantics are changed.
- Task 10 `replay_trained_model` is touched.
- API / frontend / migration code is introduced without a separate amendment.
- Issue #21 / #33 / #36 / #38 is closed.
- PR is marked Ready before Charles authorizes freeze + Ready.

---

## Refs

- **Issue #21** — TASK-011 umbrella, OPEN
- **Issue #29** — Phase 3.1, CLOSED / COMPLETED
- **Issue #33** — Phase 4 planning, OPEN
- **Issue #34** — Phase 4a design planning, CLOSED / COMPLETED
- **Issue #36** — Phase 4b design planning, CLOSED / COMPLETED
- **Issue #38** — Phase 4c planning, OPEN
- **PR #30** — Phase 3.1 implementation, MERGED
- **PR #35** — Phase 4a design amendment, MERGED
- **PR #37** — Phase 4b design amendment, MERGED
- **PR #40** — Phase 4b implementation, MERGED (merge commit `18d3043d4e03ada82f89f2448222afbfbca1e874`)
- **Freeze comment 4889240526** on PR #35 (Phase 4a)
- **Freeze comment 4889788635** on PR #37 (Phase 4b)
- **Issue #34 closeout comment 4889491442**
- **Phase 4a Design Amendment Content SHA:** `632e2e1f2880c9a6d7b87ee9f90565223ece69aaee43bea620f526c1fe1c8f3c`
- **Phase 4b Design Amendment Content SHA:** `7ed7cb567c72f107b4a83ed64f0ed66309fdd98049110afa4ec3831598e7c63a`
- **Phase 4a docs:** `docs/task-11-phase4a-evaluation-mask-amendment.md`
- **Phase 4b docs:** `docs/task-11-phase4b-metric-formulas-amendment.md`
- **Phase 4a Frozen Authority Base SHA:** `7340ec51865645a2c06b2d2e1e54d24cd457c831` (preserved, not rotated)
- **Phase 4a Frozen Amendment Content SHA:** `f2896ae475d4e007fb2e54ad07f294e718d1e171` (preserved, not rotated)
- **Phase 4b PR #37 merge commit:** `6b59092933205ba4b0e37f3539c8eaca2a506246`
- **Phase 4b implementation PR #40 merge commit:** `18d3043d4e03ada82f89f2448222afbfbca1e874`
- **Task 10 `replay_trained_model`:** explicitly deferred to a later independent design decision
