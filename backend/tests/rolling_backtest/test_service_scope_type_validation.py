"""P1 regression tests for TASK-011 Phase 4c-1 service-layer scope-type validation.

These tests guard the contract that ``compute_metrics`` MUST translate any
invalid ``scope`` payload — including non-mapping values such as ``None``,
``str``, ``list``, ``int`` — into a clean
``ServiceContractError(kind="invalid_scope", ...)`` rather than leaking a
raw ``AttributeError`` / ``TypeError`` from internal ``scope.get(...)``
calls that fire before ``_validate_scope(scope)`` is reached.

Background
----------
Inside ``backend.app.rolling_backtest.service.compute_metrics`` the order
of operations on the ``scope`` parameter is:

1.  ``scope_id = str(scope.get("node", "")) if "node" in scope else ""``
    (early read of ``scope.get`` for diagnostic / scope_id binding)
2.  ``_validate_scope(scope)``
    (the dedicated validator that maps non-mapping payloads to
    ``ServiceContractError(kind="invalid_scope")``)

Step 1 executes before step 2, which means a non-mapping ``scope``
(``None``, ``str``, ``list``, ``int``) currently surfaces a raw
``AttributeError`` / ``TypeError`` instead of the contractually promised
``ServiceContractError(kind="invalid_scope")``.

These tests document the contract: callers must receive
``ServiceContractError(kind="invalid_scope")`` regardless of which form
the bad ``scope`` takes. If the test ever regresses (raw
``AttributeError`` / ``TypeError``), the failure must be fixed at the
service layer (move ``_validate_scope(scope)`` ahead of the
``scope.get(...)`` read) — never by catching the raw exception inside the
test.

Scope discipline
----------------
* File location: ``backend/tests/rolling_backtest/`` (NOT under
  ``backend/app/``, NOT under ``backend/alembic/versions/``, NOT under
  ``backend/app/models/``).
* No production-code mutation.
* No DB / network IO.
* No changes to ``compute_metrics`` public signature.
"""

from __future__ import annotations

import pytest

from backend.app.rolling_backtest import (
    ServiceContractError,
    compute_metrics,
    register_materialization_provider,
)

SAMPLE_MASK_HASH = "0" * 63 + "1"  # 64-char lowercase hex
SAMPLE_RUN_ID = "run-001"


@pytest.fixture
def stub_provider() -> None:
    """Register a stub materialization provider; tear down after the test.

    Mirrors the contract of the same fixture in ``test_service.py``: the
    provider honors the typed-exception contract (run-not-found /
    mask-not-bound) and returns ``[]`` for any other (run, mask_hash)
    pair. Since these P1 tests never reach the provider (compute_metrics
    MUST reject bad scope at the validation boundary), the
    ``list`` branch is unreachable but kept for parity.
    """

    def provider(run_id: str, mask_hash: str) -> list:
        del run_id, mask_hash
        return []

    register_materialization_provider(provider)
    try:
        yield None
    finally:
        register_materialization_provider(None)


INVALID_SCOPE_PAYLOADS: list[tuple[str, object]] = [
    ("none", None),
    ("str", "not-a-mapping"),
    ("list", [1, 2, 3]),
    ("int", 42),
    ("tuple", ("a", "b")),
    ("bool", True),
]


@pytest.mark.parametrize(
    "label,invalid_scope",
    INVALID_SCOPE_PAYLOADS,
    ids=[label for label, _ in INVALID_SCOPE_PAYLOADS],
)
def test_compute_metrics_invalid_scope_type_raises_invalid_scope_contract_error(
    label: str,
    invalid_scope: object,
    stub_provider: None,
) -> None:
    """P1 regression: non-mapping ``scope`` MUST surface as
    ``ServiceContractError(kind="invalid_scope")`` — never as raw
    ``AttributeError`` / ``TypeError`` leaking out of the service layer.
    """
    with pytest.raises(ServiceContractError) as exc_info:
        compute_metrics(
            run_id=SAMPLE_RUN_ID,
            scope=invalid_scope,  # type: ignore[arg-type]
            mask_hash=SAMPLE_MASK_HASH,
        )
    assert exc_info.value.kind == "invalid_scope", (
        f"P1 regression: compute_metrics(scope={label!r}) raised "
        f"ServiceContractError with kind={exc_info.value.kind!r}; "
        f"expected kind='invalid_scope'. The service layer is leaking a "
        f"non-contract error for non-mapping scope payloads."
    )
