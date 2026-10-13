"""Independent encoding and immutable-artifact guards for the R2 pipeline."""

import hashlib
from pathlib import Path

import pytest

from research.blueberry_vision.r2_common import canonical_hash, read_json, write_json_new


def test_canonical_bytes_use_r1_convention() -> None:
    expected_bytes = b'{"a":1,"b":2}'
    assert canonical_hash({"b": 2, "a": 1}) == hashlib.sha256(expected_bytes).hexdigest()


def test_output_cannot_replace_an_existing_artifact(tmp_path: Path) -> None:
    target = tmp_path / "artifact.json"
    write_json_new(target, {"value": 1})
    before = target.read_bytes()
    with pytest.raises(FileExistsError):
        write_json_new(target, {"value": 2})
    assert target.read_bytes() == before


@pytest.mark.parametrize("content", ['{"a":1,"a":2}', '{"a":NaN}', '{"a":1e999}', "[]"])
def test_json_ambiguity_and_overflow_are_rejected(tmp_path: Path, content: str) -> None:
    target = tmp_path / "bad.json"
    target.write_text(content)
    with pytest.raises(ValueError):
        read_json(target)


def test_json_size_is_bounded(tmp_path: Path) -> None:
    target = tmp_path / "large.json"
    target.write_text('{"a":123456789}')
    with pytest.raises(ValueError, match="JSON_SIZE_LIMIT"):
        read_json(target, max_bytes=3)
