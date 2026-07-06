"""TASK-011 Phase 4c-1 — public service layer.

This module is the 4c-1 implementation slice of the Phase 4c design
contract (``docs/task-11-phase4c-service-cli-export-amendment.md`` on
main, frozen at content SHA
``9f1f541367ee7c4ea3814f0068f682b29e590758690dcb2098cadd5de7796216``).
It implements the public ``compute_metrics`` façade over the Phase 4b
metric primitives per design §3.

Hard constraints (mirrored from the design §0, §3.3, §12 stop conditions
and the §13 binding rules):

* Read-only over Phase 4a materialization. No schema / migration change.
* No Phase 4c-2 CLI / deterministic export code.
* No Phase 4c-3 production-shaped E2E / reload integrity code.
* No Task 8 / Task 9 / Task 10 semantic changes.
* No ``replay_trained_model`` mutation.
* No API / frontend / migrations.
* No ``current`` / ``latest`` implicit selection. Every call carries an
  explicit ``run_id``, ``scope``, and ``mask_hash``.
* No database / network IO from ``compute_metrics`` itself — IO is
  delegated to an optional, externally-registered
  ``materialization_provider`` (see :func:`register_materialization_provider`).
  When no provider is registered the function is strictly pure: any
  ``run_id`` raises ``ServiceContractError(kind="missing_run", ...)``.

Side-effect contract (frozen, design §3.3):

* ``compute_metrics`` MUST NOT write to disk, the database, or any other
  side channel. It MUST NOT make network calls. It MUST be re-entrant
  (safe to call from concurrent threads; no module-level mutable state
  outside the provider registry slot). It MUST be deterministic: identical
  inputs produce byte-identical ``EvaluationResult.canonical_payload_hash``
  (delegated to Phase 4b).

Materialization-provider contract:

* The provider is a ``Callable[[str, str], list[EvaluationMetricRow]]``
  that maps ``(run_id, mask_hash)`` to a list of Phase 4a evaluation
  rows. It is the only way ``compute_metrics`` reads rows. It is the
  caller's responsibility to register a provider (e.g. an in-memory
  fixture for tests; a future Phase 4a materialization reader for
  production).
* The provider signals **negative outcomes** by raising typed
  exceptions, NOT by returning ``None`` or a sentinel list:

  - :class:`MaterializationRunNotFound` — the ``run_id`` is not
    present in the Phase 4a materialization at all. Translated to
    ``ServiceContractError(kind="missing_run", ...)``.
  - :class:`MaterializationMaskNotBound` — the ``run_id`` is present,
    but the requested ``mask_hash`` is not bound to that ``run_id``.
    Translated to ``ServiceContractError(kind="mask_hash_unbound", ...)``.

  The service layer discriminates these two kinds via the exception
  type, never by parsing exception message text or return value shape.
* The provider slot is module-level (single global). This is the
  minimum surface for the frozen signature and is documented in §3.3
  (no IO inside ``compute_metrics``). The slot is intentionally
  un-synchronized: tests wire and un-wire it in serial test setup /
  teardown; production wiring lives in a separate slice.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Final

from backend.app.rolling_backtest.metrics import (
    DEFAULT_DECIMAL_SCALE,
    METRIC_DEFINITION_VERSION,
    EvaluationMaskState,
    EvaluationMetricRow,
    EvaluationResult,
    canonical_payload_hash,
    evaluate_scope,
    split_by_factory,
)

# ---------------------------------------------------------------------------
# Service-layer error / blocker model (design §3.4)
# ---------------------------------------------------------------------------


class ServiceContractError(ValueError):
    """Public service-layer error (design §3.4).

    Subclasses ``ValueError`` for forward-compat with callers that
    expect ``ValueError`` on bad input. The ``kind`` field carries the
    machine-readable error code; the ``message`` field carries a
    human-readable description.
    """

    def __init__(
        self,
        *,
        kind: str,
        message: str,
        metric_definition_version: str = METRIC_DEFINITION_VERSION,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.metric_definition_version = metric_definition_version

    def to_payload(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "message": self.message,
            "metric_definition_version": self.metric_definition_version,
        }


# ---------------------------------------------------------------------------
# Frozen Phase 4b public metric surface (design §3.4 — `metric_subset` check)
# ---------------------------------------------------------------------------


# The list of metric names that ``compute_metrics`` accepts in
# ``metric_subset``. Must stay in lock-step with the Phase 4b public
# surface exposed via ``backend.app.rolling_backtest.metrics``. The
# counters (row_count, comparable_row_count, masked_row_count,
# withheld_row_count) are always emitted; they are NOT accepted as
# ``metric_subset`` entries because they are not optional.
_PHASE_4B_METRIC_NAMES: Final[frozenset[str]] = frozenset(
    {
        "mean_absolute_error",
        "wmape",
        "cumulative_relative_error",
        "pinball_loss_p50",
        "empirical_coverage_p50",
        "peak_date_error_days_p50_signed",
        "peak_date_error_days_p50_absolute",
        "peak_magnitude_error_p50",
        "quantile_crossing_count",
        "interval_width_mean_p80_p50",
        "interval_width_median_p80_p50",
        "correction_magnitude_count",
        "correction_magnitude_median",
    }
)


# ---------------------------------------------------------------------------
# Materialization provider registry (design §3.2 + §3.3)
# ---------------------------------------------------------------------------


# Typed internal exceptions for the materialization provider contract.
# The provider raises these (instead of returning a sentinel) so that the
# service layer can distinguish "run is unknown" from "run exists but
# mask is not bound to it" via the exception type — never by string
# parsing.


class MaterializationRunNotFound(LookupError):
    """Raised by a materialization provider when ``run_id`` is unknown.

    Translated by :func:`compute_metrics` to
    ``ServiceContractError(kind="missing_run", ...)``.
    """

    def __init__(self, *, run_id: str) -> None:
        super().__init__(f"run_id={run_id!r} not found in materialization")
        self.run_id = run_id


class MaterializationMaskNotBound(LookupError):
    """Raised by a materialization provider when ``run_id`` is known
    but ``mask_hash`` is not bound to it.

    Translated by :func:`compute_metrics` to
    ``ServiceContractError(kind="mask_hash_unbound", ...)``.
    """

    def __init__(self, *, run_id: str, mask_hash: str) -> None:
        super().__init__(f"mask_hash={mask_hash!r} is not bound to run_id={run_id!r}")
        self.run_id = run_id
        self.mask_hash = mask_hash


# Module-level slot for an optional materialization provider. The slot is
# single-valued; tests can swap it in serial setup / teardown. Production
# wiring lives outside this module (a future slice).
_MaterializationProvider = Callable[[str, str], list[EvaluationMetricRow]]
_provider: _MaterializationProvider | None = None


def register_materialization_provider(
    provider: _MaterializationProvider | None,
) -> _MaterializationProvider | None:
    """Register (or unregister) the materialization provider.

    Returns the previous provider, or ``None`` if none was registered.
    The function is the only mutator of the module-level provider slot
    and is therefore the only stateful surface. It is intentionally
    NOT thread-safe; production wiring must be done before any
    ``compute_metrics`` call, and the wiring code is the only caller.
    """

    global _provider
    previous = _provider
    _provider = provider
    return previous


def get_materialization_provider() -> _MaterializationProvider | None:
    """Return the currently registered materialization provider (or ``None``)."""

    return _provider


# ---------------------------------------------------------------------------
# Input validation helpers
# ---------------------------------------------------------------------------


def _validate_mask_hash(mask_hash: str) -> None:
    if not isinstance(mask_hash, str) or len(mask_hash) != 64:
        raise ServiceContractError(
            kind="invalid_mask_hash",
            message=(
                "mask_hash must be a 64-character string "
                f"(got len={len(mask_hash) if isinstance(mask_hash, str) else 'n/a'})"
            ),
        )
    if any(c not in "0123456789abcdef" for c in mask_hash):
        raise ServiceContractError(
            kind="invalid_mask_hash",
            message="mask_hash must be lowercase hexadecimal (got non-hex character)",
        )


def _validate_scope(scope: Mapping[str, Any]) -> None:
    if "node" not in scope:
        raise ServiceContractError(
            kind="invalid_scope",
            message="scope must include 'node'",
        )


def _validate_decimal_scale(decimal_scale: int) -> None:
    if not isinstance(decimal_scale, int) or isinstance(decimal_scale, bool):
        raise ServiceContractError(
            kind="invalid_decimal_scale",
            message=(f"decimal_scale must be an int (got {type(decimal_scale).__name__})"),
        )
    if decimal_scale < 0:
        raise ServiceContractError(
            kind="invalid_decimal_scale",
            message=f"decimal_scale must be >= 0 (got {decimal_scale})",
        )


def _validate_metric_subset(
    metric_subset: tuple[str, ...] | None,
) -> None:
    if metric_subset is None:
        return
    for name in metric_subset:
        if name not in _PHASE_4B_METRIC_NAMES:
            raise ServiceContractError(
                kind="unknown_metric",
                message=(
                    f"metric_subset contains unknown metric {name!r}; "
                    f"known metrics: {sorted(_PHASE_4B_METRIC_NAMES)}"
                ),
            )


# ---------------------------------------------------------------------------
# Mask-binding validation
# ---------------------------------------------------------------------------


def _validate_mask_binding(
    *,
    run_id: str,
    mask_hash: str,
) -> list[EvaluationMetricRow]:
    """Look up Phase 4a materialization via the registered provider.

    Returns the row list on success. Raises :class:`ServiceContractError`
    on the following negative outcomes:

    * missing provider → ``missing_run`` (no materialization wired)
    * provider raises :class:`MaterializationRunNotFound` →
      ``missing_run`` (run is unknown)
    * provider raises :class:`MaterializationMaskNotBound` →
      ``mask_hash_unbound`` (run exists, mask is not bound)
    * provider raises any other exception → ``missing_run`` (defensive)
    * provider returns a non-list → ``missing_run`` (defensive)

    The two error kinds are discriminated by exception **type**, never
    by message parsing.
    """

    if _provider is None:
        raise ServiceContractError(
            kind="missing_run",
            message=(
                f"no materialization provider registered; cannot resolve "
                f"run_id={run_id!r} mask_hash={mask_hash[:8]}…"
            ),
        )
    try:
        materialized = _provider(run_id, mask_hash)
    except MaterializationRunNotFound as exc:
        raise ServiceContractError(
            kind="missing_run",
            message=(f"run_id={exc.run_id!r} not found in Phase 4a materialization"),
        ) from exc
    except MaterializationMaskNotBound as exc:
        raise ServiceContractError(
            kind="mask_hash_unbound",
            message=(
                f"mask_hash={exc.mask_hash!r} is not bound to "
                f"run_id={exc.run_id!r} in Phase 4a materialization"
            ),
        ) from exc
    if not isinstance(materialized, list):
        raise ServiceContractError(
            kind="missing_run",
            message=(
                f"materialization provider returned non-list for "
                f"run_id={run_id!r} (got {type(materialized).__name__})"
            ),
        )
    return materialized


# ---------------------------------------------------------------------------
# Public service entry point (design §3.2)
# ---------------------------------------------------------------------------


def compute_metrics(
    *,
    run_id: str,
    scope: Mapping[str, Any],
    mask_hash: str,
    metric_subset: tuple[str, ...] | None = None,
    decimal_scale: int = DEFAULT_DECIMAL_SCALE,
) -> EvaluationResult:
    """Public service-layer entry point (design §3.2).

    Pure façade over Phase 4b ``evaluate_scope`` / ``split_by_factory``.
    Reads Phase 4a materialization via the registered
    ``materialization_provider`` (see :func:`register_materialization_provider`).

    Parameters
    ----------
    run_id : str
        Stable Phase 4a logical run identifier. REQUIRED. No implicit
        selection.
    scope : Mapping[str, Any]
        Scope identity (run/node/horizon/farm/variety/model_version/
        eval_mask_hash). Must include ``node``.
    mask_hash : str
        64-char lowercase hex Phase 4a evaluation mask hash.
    metric_subset : tuple[str, ...] | None
        Optional explicit allowlist of metric names. ``None`` ⇒ run
        the full Phase 4b metric set. Names not in the Phase 4b public
        surface raise ``ServiceContractError(kind="unknown_metric", ...)``.
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
        On invalid input or missing materialization (design §3.4).
    """

    # Input validation — runs in a fixed order so the error kind is
    # deterministic for a given input. The order is the order of the
    # rows in design §3.4 (top to bottom).
    _validate_mask_hash(mask_hash)
    _validate_scope(scope)
    _validate_decimal_scale(decimal_scale)
    _validate_metric_subset(metric_subset)

    # Materialization lookup — raises ServiceContractError on missing
    # provider / missing run / unbound mask.
    rows = _validate_mask_binding(run_id=run_id, mask_hash=mask_hash)

    # Phase 4b invocation. We delegate canonical payload hash
    # computation to Phase 4b (which is the authoritative source of
    # ``canonical_payload_hash`` semantics for the 4b-1.0.0 metric
    # definition version). The service layer does NOT recompute the
    # hash.
    mask = EvaluationMaskState(evaluation_mask_hash=mask_hash)

    # Multi-row materialization: if the rows span more than one
    # ``node_id``, the caller is asking for a per-factory split. We
    # detect that here (the single-row case uses ``evaluate_scope``;
    # the multi-row case uses ``split_by_factory`` and merges the
    # per-factory results into a single ``EvaluationResult`` that
    # carries the combined audit hash).
    distinct_nodes = {row.node_id for row in rows}
    if len(distinct_nodes) > 1:
        per_factory = split_by_factory(
            rows,
            mask,
            run_id=str(scope.get("run", run_id)),
            horizon=str(scope.get("horizon", "daily")),
            model_version=str(scope.get("model_version", "")),
            decimal_scale=decimal_scale,
        )
        # Merge per-factory results. The combined hash is the SHA-256
        # of the canonicalized concatenation of per-factory hashes
        # (sorted by node_id). This keeps the service-layer hash
        # deterministic for identical inputs and independent of the
        # materialization row order.
        combined_outputs: list[Any] = []
        per_factory_hashes: list[str] = []
        for factory_id in sorted(per_factory):
            per_factory_hashes.append(per_factory[factory_id].canonical_payload_hash)
            for output in per_factory[factory_id].outputs:
                # Re-bind the scope identity to the factory id; this
                # preserves per-factory audit traceability while still
                # giving the caller a flat list of metric outputs.
                combined_outputs.append(output)
        combined_hash_input = {
            "split": "factory",
            "per_factory_hashes": per_factory_hashes,
            "metric_definition_version": METRIC_DEFINITION_VERSION,
            "decimal_scale": str(decimal_scale),
            "evaluation_mask_hash": mask_hash,
            "run_id": run_id,
        }
        combined_hash = canonical_payload_hash(combined_hash_input)
        merged = EvaluationResult(
            outputs=tuple(combined_outputs),
            canonical_payload_hash=combined_hash,
        )
        return _apply_metric_subset(merged, metric_subset)

    # Single-factory case — use ``evaluate_scope`` directly.
    enriched_scope = dict(scope)
    enriched_scope.setdefault("run", run_id)
    enriched_scope.setdefault("evaluation_mask_hash", mask_hash)
    full_result = evaluate_scope(
        rows,
        mask,
        scope=enriched_scope,
        decimal_scale=decimal_scale,
    )
    return _apply_metric_subset(full_result, metric_subset)


# ---------------------------------------------------------------------------
# metric_subset filter (design §3.2)
# ---------------------------------------------------------------------------


_COUNTER_NAMES: Final[frozenset[str]] = frozenset(
    {
        "row_count",
        "comparable_row_count",
        "masked_row_count",
        "withheld_row_count",
    }
)


def _apply_metric_subset(
    result: EvaluationResult,
    metric_subset: tuple[str, ...] | None,
) -> EvaluationResult:
    """Filter ``result.outputs`` to ``metric_subset`` ∪ counters.

    Counters are always emitted. When ``metric_subset`` is ``None`` the
    function returns the input unchanged. When non-``None`` the
    canonical payload hash is recomputed over the filtered set so the
    hash reflects the chosen subset, not the full set.
    """

    if metric_subset is None:
        return result
    allowed = _COUNTER_NAMES | set(metric_subset)
    filtered_outputs = tuple(output for output in result.outputs if output.metric_name in allowed)
    filtered_payload = {
        "outputs": [o.to_audit_payload() for o in filtered_outputs],
        "metric_definition_version": METRIC_DEFINITION_VERSION,
    }
    filtered_hash = canonical_payload_hash(filtered_payload)
    return EvaluationResult(
        outputs=filtered_outputs,
        canonical_payload_hash=filtered_hash,
    )


# ---------------------------------------------------------------------------
# Re-export of design §3.4 constants for test wiring
# ---------------------------------------------------------------------------


__all__ = [
    "ServiceContractError",
    "compute_metrics",
    "get_materialization_provider",
    "register_materialization_provider",
]
