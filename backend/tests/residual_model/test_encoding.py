from __future__ import annotations


def test_category_encoding_is_deterministic() -> None:
    from backend.app.residual_model.encoding import build_category_encoding

    encoding = build_category_encoding(
        feature_name="destination_factory_category",
        categories=["b", "a", "b", None],
        encoding_version="task10-categorical-v1",
    )

    assert encoding.ordered_known_categories == ["a", "b"]
    assert encoding.unknown_bucket_code == 2
    assert encoding.missing_bucket_code == 3


def test_unknown_category_uses_explicit_bucket() -> None:
    from backend.app.residual_model.encoding import build_category_encoding, encode_category

    encoding = build_category_encoding(
        feature_name="destination_factory_category",
        categories=["a"],
        encoding_version="task10-categorical-v1",
    )

    assert encode_category("z", encoding=encoding) == encoding.unknown_bucket_code
    assert encode_category(None, encoding=encoding) == encoding.missing_bucket_code
