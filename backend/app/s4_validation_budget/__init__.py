"""Durable PostgreSQL authority for the V0.3 S4 validation budget.

This package is deliberately separate from the candidate execution adapter.
It owns only the append-only validation event ledger and its monotonic head.
Candidate runners are integrated with this primitive by a later, separately
authorized task.
"""

from backend.app.s4_validation_budget.errors import (
    ValidationBudgetBlocked,
    ValidationBudgetError,
)
from backend.app.s4_validation_budget.persistence import (
    S4ValidationBudgetRepository,
)
from backend.app.s4_validation_budget.schemas import (
    StartedEventCommand,
    StoredValidationEvent,
    TerminalEventCommand,
    ValidationBudgetState,
    VerifiedValidationBudgetState,
)

__all__ = [
    "S4ValidationBudgetRepository",
    "StartedEventCommand",
    "StoredValidationEvent",
    "TerminalEventCommand",
    "ValidationBudgetBlocked",
    "ValidationBudgetError",
    "ValidationBudgetState",
    "VerifiedValidationBudgetState",
]
