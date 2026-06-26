from __future__ import annotations

from collections.abc import Iterable

from backend.app.residual_model.schemas import CategoryEncoding


def build_category_encoding(
    *,
    feature_name: str,
    categories: Iterable[str | None],
    encoding_version: str,
) -> CategoryEncoding:
    known_categories = sorted({item for item in categories if item is not None})
    return CategoryEncoding(
        feature_name=feature_name,
        ordered_known_categories=known_categories,
        unknown_bucket_code=len(known_categories),
        missing_bucket_code=len(known_categories) + 1,
        encoding_version=encoding_version,
    )


def encode_category(value: str | None, *, encoding: CategoryEncoding) -> int:
    if value is None:
        return encoding.missing_bucket_code
    try:
        return encoding.ordered_known_categories.index(value)
    except ValueError:
        return encoding.unknown_bucket_code

