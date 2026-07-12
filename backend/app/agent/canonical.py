"""TASK-013 Slice A — thin wrapper around the existing canonical contract.

The Agent layer MUST NOT introduce a competing canonicalization standard.  This
module re-exports the existing helpers from
``backend.app.rolling_backtest.canonical`` and provides three Agent-specific
helpers that simply call those underlying functions:

* :func:`canonical_request_hash` — sha256 of the canonical JSON of a
  :class:`~backend.app.agent.schemas.NormalizedAgentRequest`.
* :func:`advanced_overrides_hash` — sha256 of the canonical JSON of an
  :class:`~backend.app.agent.schemas.AdvancedOverrides`.
* :func:`parameters_hash` — sha256 of the canonical JSON of a list of
  :class:`~backend.app.agent.schemas.ParameterEstimate`.

All three reuse :func:`backend.app.rolling_backtest.canonical.sha256_payload`
which itself delegates to the project-wide canonical contract.  No new
canonicalization rule is introduced here.
"""

from __future__ import annotations

from backend.app.rolling_backtest.canonical import (
    canonical_json_dumps,
    canonical_json_value,
    sha256_payload,
)

__all__ = [
    "canonical_json_dumps",
    "canonical_json_value",
    "sha256_payload",
    "canonical_request_hash",
    "advanced_overrides_hash",
    "parameters_hash",
]


def canonical_request_hash(normalized_request: object) -> str:
    """sha256 over the canonical JSON of a ``NormalizedAgentRequest``."""

    return sha256_payload(normalized_request)


def advanced_overrides_hash(overrides: object | None) -> str:
    """sha256 over the canonical JSON of ``AdvancedOverrides`` (``None`` allowed)."""

    return sha256_payload(overrides)


def parameters_hash(parameters: object) -> str:
    """sha256 over the canonical JSON of a list of ``ParameterEstimate``."""

    return sha256_payload(parameters)
