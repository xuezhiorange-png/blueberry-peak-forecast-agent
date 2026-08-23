"""Deterministic identity hashing for S3-A daily rowsets."""

from __future__ import annotations

from backend.app.rolling_backtest.canonical import sha256_payload
from backend.app.s3_daily_rowset.schemas import (
    DailyRow,
    DatasetIdentity,
    EvaluationInstanceCell,
    WindowKind,
)

ROWSET_IDENTITY_VERSION = "v0-3-s3-a-rowset-identity-v1"


def daily_row_identity_payload(row: DailyRow) -> dict[str, object]:
    return {
        "actual_harvest_quantity_kg": row.actual_harvest_quantity_kg,
        "business_date": row.business_date,
        "daily_row_status": row.daily_row_status,
        "forecast_harvest_quantity_kg": row.forecast_harvest_quantity_kg,
    }


def compute_rowset_identity_sha256(
    *,
    dataset_identity: DatasetIdentity,
    cell: EvaluationInstanceCell,
    window_kind: WindowKind,
    evaluation_window_days: int | None,
    window_start_date: str | None,
    window_end_date: str | None,
    daily_rows: tuple[DailyRow, ...],
) -> str:
    payload = {
        "dataset_id": dataset_identity.dataset_id,
        "dataset_version": dataset_identity.dataset_version,
        "materialized_dataset_identity_sha256": (
            dataset_identity.materialized_dataset_identity_sha256
        ),
        "evaluation_instance": {
            "farm": cell.farm,
            "forecast_cutoff_at": cell.forecast_cutoff_at,
            "forecast_quantile": cell.forecast_quantile,
            "model_id": cell.model_id,
            "season": cell.season,
            "subfarm": cell.subfarm,
            "variety": cell.variety,
        },
        "evaluation_window_days": evaluation_window_days,
        "ordered_daily_rows": [daily_row_identity_payload(row) for row in daily_rows],
        "rowset_identity_version": ROWSET_IDENTITY_VERSION,
        "window_end_date": window_end_date,
        "window_kind": window_kind,
        "window_start_date": window_start_date,
    }
    return sha256_payload(payload)
