"""Source admission uses declared licenses, never search availability as permission."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from research.blueberry_vision.r3 import sources


def _commons(
    license_name: str = "CC0",
    license_url: str = "https://creativecommons.org/publicdomain/zero/1.0/",
) -> dict[str, Any]:
    return {
        "query": {
            "pages": {
                "12": {
                    "pageid": 12,
                    "title": "File:Blueberries-In-Pack.jpg",
                    "revisions": [{"revid": 9}],
                    "imageinfo": [
                        {
                            "url": "https://upload.wikimedia.org/wikipedia/commons/0/0b/Blueberries-In-Pack.jpg",
                            "descriptionurl": "https://commons.wikimedia.org/wiki/File:Blueberries-In-Pack.jpg",
                            "size": 100,
                            "width": 10,
                            "height": 10,
                            "extmetadata": {
                                "LicenseShortName": {"value": license_name},
                                "LicenseUrl": {"value": license_url},
                                "Artist": {"value": "Author"},
                                "Restrictions": {"value": ""},
                                "AttributionRequired": {"value": "false"},
                            },
                        }
                    ],
                }
            }
        }
    }


def test_commons_license_requires_matching_authoritative_terms() -> None:
    row = sources.parse_commons(_commons())[0]
    assert row["license_status"] == "LICENSE_VERIFIED"
    assert row["research_use"] is True
    assert row["commercial_use"] is True
    assert row["has_per_fruit_annotations"] is False
    assert row["purpose"] == "PUBLIC_EXTERNAL_BENCHMARK"
    assert row["SYNTHETIC"] is False
    for url in [
        "https://evil.example/license",
        "https://creativecommons.org/licenses/by-nc/4.0/",
        "https://creativecommons.org/licenses/by/4.0/",
    ]:
        assert (
            sources.parse_commons(_commons(license_url=url))[0]["license_status"]
            == "LICENSE_UNVERIFIED"
        )


@pytest.mark.parametrize(
    "license_name", ["All rights reserved", "Public domain", "CC BY-NC 4.0", "CC BY-ND 4.0", ""]
)
def test_unknown_noncommercial_or_nonderivative_license_not_auto_admitted(
    license_name: str,
) -> None:
    row = sources.parse_commons(_commons(license_name=license_name))[0]
    assert row["license_status"] == "LICENSE_UNVERIFIED"
    assert row["research_use"] is None


def test_restrictions_block_automatic_admission() -> None:
    payload = _commons()
    payload["query"]["pages"]["12"]["imageinfo"][0]["extmetadata"]["Restrictions"] = {
        "value": "Permission required"
    }
    assert sources.parse_commons(payload)[0]["license_status"] == "LICENSE_UNVERIFIED"


def test_noncommercial_is_explicit_pending_company_purpose() -> None:
    row = sources.parse_zenodo(
        {
            "id": 14002517,
            "metadata": {
                "title": "BlueberryDCM",
                "license": {"id": "cc-by-nc-4.0"},
                "creators": [{"name": "Author", "affiliation": "University"}],
            },
            "files": [],
        }
    )
    assert row["license_status"] == "LICENSE_VERIFIED_USE_RESTRICTED"
    assert row["commercial_use"] is False
    assert row["research_use"] == "NONCOMMERCIAL_ONLY"
    assert row["download_admission"] == "BLOCKED_PENDING_PURPOSE_OR_PERMISSION"


def test_code_archive_license_not_copied_to_underlying_images() -> None:
    row = sources.parse_zenodo(
        {
            "id": 10522314,
            "metadata": {
                "title": "Experiments Code & Results",
                "license": {"id": "cc-by-4.0"},
                "creators": [],
            },
            "files": [],
        }
    )
    assert row["license_scope"] == "DEPOSIT_CODE_AND_RESULTS_ONLY"
    assert row["image_license_status"] == "LICENSE_UNVERIFIED"
    assert row["download_admission"] == "BLOCKED_IMAGE_LICENSE_SCOPE"


@pytest.mark.parametrize(
    "url",
    [
        "http://commons.wikimedia.org/w/api.php",
        "https://localhost/a",
        "https://127.0.0.1/a",
        "https://commons.wikimedia.org.evil.example/a",
        "https://user:pass@commons.wikimedia.org/a",
        "file:///etc/passwd",
    ],
)
def test_network_endpoint_policy_rejects_nonpublic_or_unapproved_urls(url: str) -> None:
    with pytest.raises(sources.SourceError, match="SOURCE_URL_NOT_ALLOWED"):
        sources.check_public_url(url)


def test_offline_discovery_uses_persisted_evidence_without_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("network must not be used")

    monkeypatch.setattr(sources, "fetch_public", forbidden)
    result = sources.discover_sources(online=False)
    assert result["discovery_mode"] == "OFFLINE_PERSISTED_REVIEW"
    assert len(result["sources"]) >= 4
    assert all(row["purpose"] == "PUBLIC_EXTERNAL_BENCHMARK" for row in result["sources"])


def test_download_rejects_unverified_before_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    row = sources.parse_commons(_commons("Unknown"))[0]
    registry = {"sources": [row]}
    monkeypatch.setattr(sources, "fetch_public", lambda *a, **k: pytest.fail("unlicensed download"))
    with pytest.raises(sources.SourceError, match="LICENSE_NOT_ADMITTED"):
        sources.download_public_pilot(registry, tmp_path / "download", [row["source_id"]])


def test_download_limit_and_source_id_validation(tmp_path: Path) -> None:
    row = sources.parse_commons(_commons())[0]
    registry = {"sources": [row]}
    with pytest.raises(sources.SourceError, match="PILOT_IMAGE_LIMIT"):
        sources.download_public_pilot(registry, tmp_path / "many", [row["source_id"]] * 101)
    with pytest.raises(sources.SourceError, match="SOURCE_ID_UNKNOWN"):
        sources.download_public_pilot(registry, tmp_path / "missing", ["unknown"])
    with pytest.raises(sources.SourceError, match="SOURCE_ID_DUPLICATED"):
        sources.download_public_pilot(registry, tmp_path / "dup", [row["source_id"]] * 2)


def test_download_reads_pixels_records_hash_unknown_times_and_no_gt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from io import BytesIO

    from PIL import Image

    image = Image.new("RGB", (10, 10), (30, 80, 130))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    pixels = buffer.getvalue()
    row = sources.parse_commons(_commons())[0]
    row["asset_size_bytes"] = len(pixels)
    row["download_url"] = "https://upload.wikimedia.org/wikipedia/commons/example.png"
    monkeypatch.setattr(sources, "fetch_public", lambda *a, **k: pixels)
    index = sources.download_public_pilot(
        {"sources": [row]}, tmp_path / "pilot", [row["source_id"]]
    )
    item = index["images"][0]
    assert item["observed_at"] is None
    assert item["base_identity"]["status"] == "UNRESOLVED"
    assert item["GT_status"] == "MISSING"
    assert item["annotations"] is None
    assert item["SYNTHETIC"] is False
    assert len(item["asset_sha256"]) == 64
    assert json.loads((tmp_path / "pilot/source_index.json").read_text())["image_count"] == 1
    with pytest.raises(FileExistsError):
        sources.download_public_pilot({"sources": [row]}, tmp_path / "pilot", [row["source_id"]])


def test_open_source_page_phrase_not_legal_license() -> None:
    row = sources.parse_roboflow_page(
        b'<meta name="description" content="118 open source Blueberry images and annotations">'
    )
    assert row["image_count"] == 118
    assert row["license_status"] == "LICENSE_UNVERIFIED"
    assert row["download_admission"] == "BLOCKED_LICENSE_UNVERIFIED"
    assert row["research_use"] is None


def test_redirect_is_checked_before_following() -> None:
    from urllib.request import Request

    handler = sources._PublicRedirect()
    with pytest.raises(sources.SourceError, match="SOURCE_URL_NOT_ALLOWED"):
        handler.redirect_request(
            Request("https://commons.wikimedia.org/a"),
            None,
            302,
            "Found",
            {},
            "http://127.0.0.1/private",
        )


def test_source_id_cannot_be_used_as_path_traversal(tmp_path: Path) -> None:
    row = sources.parse_commons(_commons())[0]
    row["source_id"] = "../../escape"
    with pytest.raises(sources.SourceError, match="SOURCE_ID_INVALID"):
        sources.download_public_pilot({"sources": [row]}, tmp_path / "download", ["../../escape"])
