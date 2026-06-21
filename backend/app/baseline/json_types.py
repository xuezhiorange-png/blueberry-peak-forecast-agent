from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
from typing import cast

import numpy as np

from backend.app.baseline.schemas import BacktestResultRow

type JsonScalar = None | str | bool | int | float
type JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


def canonical_json_value(value: object) -> JsonValue:
    if isinstance(value, np.generic):
        return canonical_json_value(value.item())
    if value is None or isinstance(value, (str, bool, int, float)):
        return cast(JsonValue, value)
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [canonical_json_value(item) for item in value]
    if isinstance(value, dict):
        canonical_dict: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"JSON object keys must be str, got {type(key).__name__}")
            canonical_dict[key] = canonical_json_value(item)
        return canonical_dict
    raise TypeError(f"Unsupported JSON value type: {type(value).__name__}")


def canonicalize_result_row(row: BacktestResultRow) -> BacktestResultRow:
    return replace(
        row,
        input_features=cast(dict[str, object], canonical_json_value(row.input_features)),
        model_metadata=cast(dict[str, object], canonical_json_value(row.model_metadata)),
        training_season_codes=[str(item) for item in row.training_season_codes],
    )
