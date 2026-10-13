"""Use a licensed real CC0 preview already committed by R3; no network or fake GT."""

import base64
import json
import re
from pathlib import Path

import pytest

from research.blueberry_vision.r2_common import file_hash, read_json
from research.blueberry_vision.r3.ingestion import import_images

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def public_preview(tmp_path):
    html = (ROOT / "examples/r3/real_review.html").read_text()
    match = re.search(
        r'<script id="report-data" type="application/json">(.*?)</script>', html, re.DOTALL
    )
    assert match
    report = json.loads(match.group(1))
    row = next(row for row in report["images"] if row["source_id"] == "commons-15928839")
    root = tmp_path / "authorized-real-preview"
    root.mkdir()
    path = root / "preview.jpg"
    path.write_bytes(base64.b64decode(row["preview"].split(",", 1)[1]))
    original = read_json(ROOT / "evidence/r3/pilot_dataset_manifest.json")
    source = next(s for s in original["sources"] if s["source_id"] == row["source_id"])
    dataset = import_images(
        root,
        {
            "purpose": "PUBLIC_EXTERNAL_BENCHMARK",
            "SYNTHETIC": False,
            "dataset_id": "real-CC0-preview-engineering-regression-not-GT",
            "dataset_version": "4.0.0-engineering-real-preview",
            "images": [
                {
                    "image_id": "public-cc0-preview",
                    "asset_ref": path.name,
                    "asset_sha256": file_hash(path),
                    "source_id": source["source_id"],
                    "original_asset_sha256": row["asset_sha256"],
                }
            ],
        },
        {"sources": [source]},
        tmp_path / "imported",
    )
    return dataset, root
