from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any

import numpy as np

from backend.app.residual_model.canonical import canonical_payload_hash
from backend.app.residual_model.config import ResidualModelConfig
from backend.app.residual_model.encoding import build_category_encoding, encode_category
from backend.app.residual_model.feature_registry import feature_definition_map
from backend.app.residual_model.schemas import (
    CategoryEncoding,
    FeatureValue,
    ResidualTrainingManifestRow,
)


def training_signature(
    *,
    config_hash: str,
    manifest_hash: str,  # noqa: ARG001 — kept for backward compatibility
    rows: list[ResidualTrainingManifestRow],
) -> str:
    """Compute the canonical training signature.

    The signature identifies a training INTENT (which config + which
    upstream runs + which target dates) — it does NOT include
    ``manifest_hash`` because the manifest_hash is a content digest of
    the rows, and two requests with the same intent but different row
    content must collide on signature to be detectable as a
    same-signature / different-payload conflict (per PR #76 §7.1,
    §8.2).

    The ``manifest_hash`` parameter is intentionally retained for
    backward compatibility with the existing callers (which pass it
    unchanged) but it is NOT included in the hashed payload. The
    conflict detection at the persistence layer (same-signature +
    different canonical_payload_hash) is the authoritative mechanism
    for detecting manifest-content divergence.

    History note: prior rounds included ``manifest_hash`` in the
    signature, which made the signature itself content-derived and
    broke the conflict-test expectation
    (``test_training_conflict_different_canonical_payload_returns_409``):
    that test mutates ``source_run_ids`` to produce same-intent /
    different-row-content and expects 409. Under the prior logic, the
    signature changed with the manifest, so no prior run was found, so
    the conflict went undetected.
    """
    payload = {
        "config_hash": config_hash,
        "task9_runs": sorted({row.task9_run_id for row in rows}),
        "label_analytics_build_runs": sorted(
            {row.label_actual_snapshot.build_run_id for row in rows}
        ),
        "feature_analytics_build_runs": sorted(
            {row.feature_actual_snapshot.build_run_id for row in rows}
        ),
        "target_dates": sorted({row.target_arrival_local_date for row in rows}),
    }
    return canonical_payload_hash(payload)


def _string_feature_names(rows: list[ResidualTrainingManifestRow]) -> tuple[str, ...]:
    definitions = feature_definition_map()
    names: set[str] = set()
    for row in rows:
        for feature in row.feature_values:
            definition = definitions.get(feature.feature_name)
            if definition is not None and definition.dtype.value == "string":
                names.add(feature.feature_name)
    return tuple(sorted(names))


def build_category_encodings(
    rows: list[ResidualTrainingManifestRow],
    *,
    config: ResidualModelConfig,
) -> list[CategoryEncoding]:
    encodings: list[CategoryEncoding] = []
    for feature_name in _string_feature_names(rows):
        values = []
        for row in rows:
            matching = next(
                (item for item in row.feature_values if item.feature_name == feature_name),
                None,
            )
            value = matching.value if matching is not None else None
            values.append(value if isinstance(value, str) else None)
        encodings.append(
            build_category_encoding(
                feature_name=feature_name,
                categories=values,
                encoding_version=config.rules.categorical_encoding_version,
            )
        )
    return encodings


def build_training_matrix(
    rows: list[ResidualTrainingManifestRow],
    *,
    config: ResidualModelConfig,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str], list[CategoryEncoding]]:
    included_rows = [row for row in rows if row.include and row.split.value == "train"]
    feature_names = sorted(
        {feature.feature_name for row in included_rows for feature in row.feature_values}
    )
    encodings = {
        item.feature_name: item for item in build_category_encodings(included_rows, config=config)
    }
    matrix: list[list[float]] = []
    labels: list[float] = []
    weights: list[float] = []

    for row in included_rows:
        feature_map = {item.feature_name: item.value for item in row.feature_values}
        vector: list[float] = []
        for feature_name in feature_names:
            value = feature_map.get(feature_name)
            if feature_name in encodings:
                encoded = encode_category(
                    value if isinstance(value, str) else None,
                    encoding=encodings[feature_name],
                )
                vector.append(float(encoded))
            elif isinstance(value, bool):
                vector.append(1.0 if value else 0.0)
            elif isinstance(value, int):
                vector.append(float(value))
            elif isinstance(value, Decimal):
                vector.append(float(value))
            elif isinstance(value, str):
                try:
                    vector.append(float(Decimal(value)))
                except InvalidOperation as exc:
                    raise TypeError(
                        f"Unsupported string feature value for {feature_name}: {value!r}"
                    ) from exc
            elif value is None:
                vector.append(np.nan)
            else:
                raise TypeError(
                    f"Unsupported feature value type for {feature_name}: {type(value).__name__}"
                )
        matrix.append(vector)
        labels.append(float(row.residual_label_kg))
        weights.append(float(row.sample_weight))

    ordered_encodings = [encodings[name] for name in sorted(encodings)]
    return (
        np.array(matrix, dtype=float),
        np.array(labels, dtype=float),
        np.array(weights, dtype=float),
        feature_names,
        ordered_encodings,
    )


def build_prediction_matrix(
    *,
    feature_rows: list[tuple[FeatureValue, ...]],
    feature_names: list[str],
    category_encodings: list[CategoryEncoding],
) -> np.ndarray:
    encoding_map = {item.feature_name: item for item in category_encodings}
    matrix: list[list[float]] = []

    for row_features in feature_rows:
        feature_map = {item.feature_name: item.value for item in row_features}
        vector: list[float] = []
        for feature_name in feature_names:
            value = feature_map.get(feature_name)
            if feature_name in encoding_map:
                encoded = encode_category(
                    value if isinstance(value, str) else None,
                    encoding=encoding_map[feature_name],
                )
                vector.append(float(encoded))
            elif isinstance(value, bool):
                vector.append(1.0 if value else 0.0)
            elif isinstance(value, int):
                vector.append(float(value))
            elif isinstance(value, Decimal):
                vector.append(float(value))
            elif isinstance(value, str):
                try:
                    vector.append(float(Decimal(value)))
                except InvalidOperation as exc:
                    raise TypeError(
                        f"Unsupported string feature value for {feature_name}: {value!r}"
                    ) from exc
            elif value is None:
                vector.append(np.nan)
            else:
                raise TypeError(
                    f"Unsupported feature value type for {feature_name}: {type(value).__name__}"
                )
        matrix.append(vector)

    return np.array(matrix, dtype=float)


def summarize_manifest(rows: list[ResidualTrainingManifestRow]) -> dict[str, Any]:
    included = [row for row in rows if row.include]
    split_counts: dict[str, int] = defaultdict(int)
    for row in rows:
        split_counts[row.split.value] += 1
    return {
        "row_count": len(rows),
        "included_row_count": len(included),
        "excluded_row_count": len(rows) - len(included),
        "distinct_season_count": len({row.season_id for row in included}),
        "distinct_factory_count": len({row.destination_factory_id for row in included}),
        "split_counts": dict(sorted(split_counts.items())),
        "feature_names": sorted(
            {feature.feature_name for row in included for feature in row.feature_values}
        ),
    }
