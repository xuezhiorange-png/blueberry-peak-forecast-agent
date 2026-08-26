"""S3-A2 incumbent forecast V0.2/S3 SQL table-name authority."""

from __future__ import annotations

# Frozen audit authority per parent contract
# docs/v0-3/s3/s3-incumbent-forecast-v0-2-sql-table-authority-contract.md
# AUDIT_TABLE_COUNT=106; MATCH_TABLE_COUNT=0; 106-row NOT_MATCH audit not copied here.

PARENT_CONTRACT_PATH = "docs/v0-3/s3/s3-incumbent-forecast-v0-2-sql-table-authority-contract.md"
AUDIT_TABLE_COUNT = 106
MATCH_TABLE_COUNT = 0
MATCH_TABLE_NAMES: tuple[str, ...] = ()
NO_BINDABLE_V0_2_SQL_TABLE_NAME_IN_REPOSITORY = True


def bindable_table_names() -> tuple[str, ...]:
    return MATCH_TABLE_NAMES


def is_bindable(name: str) -> bool:
    return name in MATCH_TABLE_NAMES
