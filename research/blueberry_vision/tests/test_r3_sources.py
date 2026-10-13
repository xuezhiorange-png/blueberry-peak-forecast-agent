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


def test_range_reader_is_seekable_bounded_and_cache_stable() -> None:
    data = b"abcdefghij" * 1000
    calls: list[tuple[int, int]] = []

    def transport(url: str, start: int, end: int, size: int) -> bytes:
        assert size == len(data)
        calls.append((start, end))
        return data[start : end + 1]

    reader = sources.BoundedRangeFile(
        "https://zenodo.org/api/records/1/files/sample.zip/content",
        len(data),
        max_network_bytes=20_000,
        transport=transport,
    )
    assert reader.read(5) == b"abcde"
    assert reader.seek(0) == 0
    assert reader.read(5) == b"abcde"
    assert len(calls) == 1
    assert reader.seek(-4, 2) == len(data) - 4
    assert reader.read() == b"ghij"
    with pytest.raises(sources.SourceError, match="ZIP_RANGE_BOUNDS"):
        reader.seek(-1)


def test_range_reader_rejects_budget_and_large_reads_before_network() -> None:
    def forbidden(*args: Any) -> bytes:
        pytest.fail("network should be blocked before call")

    reader = sources.BoundedRangeFile(
        "https://zenodo.org/api/records/1/files/sample.zip/content",
        30_000_000,
        max_network_bytes=10,
        transport=forbidden,
    )
    with pytest.raises(sources.SourceError, match="ZIP_NETWORK_BUDGET"):
        reader.read(11)
    with pytest.raises(sources.SourceError, match="ZIP_READ_SIZE_LIMIT"):
        reader.read(21_000_000)


def test_zip_member_reader_verifies_crc_and_never_extracts_archive_paths() -> None:
    import io
    import zipfile

    blob = io.BytesIO()
    with zipfile.ZipFile(blob, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("dataset/image.jpg", b"example_image_bytes")
        z.writestr("../escape.jpg", b"unsafe")
    data = blob.getvalue()
    reader = sources.BoundedRangeFile(
        "https://zenodo.org/api/records/1/files/sample.zip/content",
        len(data),
        transport=lambda url, start, end, size: data[start : end + 1],
    )
    with zipfile.ZipFile(reader) as archive:
        assert sources.read_archive_member(archive, "dataset/image.jpg") == b"example_image_bytes"
        with pytest.raises(sources.SourceError, match="ZIP_MEMBER_PATH_UNSAFE"):
            sources.read_archive_member(archive, "../escape.jpg")


def test_mpo_first_frame_adapter_is_explicit_bounded_and_does_not_change_raw() -> None:
    from io import BytesIO

    from PIL import Image

    first = Image.new("RGB", (32, 16), (35, 90, 160))
    second = Image.new("RGB", (32, 16), (180, 30, 40))
    stream = BytesIO()
    first.save(stream, format="MPO", save_all=True, append_images=[second])
    raw = stream.getvalue()
    output, protocol = sources.normalize_public_first_frame(raw, max_long_edge=16)
    assert raw == stream.getvalue()
    assert Image.open(BytesIO(output)).format == "PNG"
    assert Image.open(BytesIO(output)).size == (16, 8)
    assert protocol["source_format"] == "MPO"
    assert protocol["selected_frame_index"] == 0
    assert protocol["geometry_scale_x"] == protocol["geometry_scale_y"] == 0.5
    assert protocol["original_asset_sha256"] != protocol["derived_asset_sha256"]
    assert protocol["source_frame_count"] == 2
    assert "SYNTHETIC" not in protocol  # Geometry processing cannot assert data origin.


def test_public_first_frame_adapter_rejects_oversize_and_unsupported_format() -> None:
    from io import BytesIO

    from PIL import Image

    with pytest.raises(sources.SourceError, match="PUBLIC_IMAGE_BYTES_LIMIT"):
        sources.normalize_public_first_frame(b"x" * 20_000_001)
    stream = BytesIO()
    Image.new("RGB", (4, 4)).save(stream, format="BMP")
    with pytest.raises(sources.SourceError, match="PUBLIC_IMAGE_FORMAT_UNSUPPORTED"):
        sources.normalize_public_first_frame(stream.getvalue())


def test_quality_candidate_bbox_conversion_has_independent_scale_golden_and_no_review(
    tmp_path: Path,
) -> None:
    from research.blueberry_vision.r2_common import file_hash, seal, write_json_new

    original = {
        "categories": [{"id": 27, "name": "source_image.JPG"}],
        "images": [{"id": 9, "file_name": "source_image.JPG"}],
        "annotations": [
            {
                "id": 111,
                "image_id": 9,
                "category_id": 27,
                "bbox": [4, 8, 12, 16],
                "segmentation": [[4, 8, 16, 8, 16, 24]],
            }
        ],
    }
    write_json_new(tmp_path / "publisher_annotations_subset.json", original)
    index = seal(
        {
            "images": [
                {
                    "publisher_image_id": 9,
                    "image_id": "quality-9",
                    "asset_ref": "derived.png",
                    "asset_sha256": "a" * 64,
                    "image_width": 10,
                    "image_height": 10,
                    "preprocessing": {"geometry_scale_x": 0.25, "geometry_scale_y": 0.25},
                }
            ],
            "publisher_coco_sha256": "b" * 64,
            "publisher_coco_member": "source.json",
            "publisher_coco_subset_sha256": file_hash(
                tmp_path / "publisher_annotations_subset.json"
            ),
        },
        "index_hash",
    )
    write_json_new(tmp_path / "source_index.json", index)
    result = sources.make_quality_bbox_draft(tmp_path)
    assert result["annotations"][0]["bbox"] == [1, 2, 3, 4]
    assert "segmentation" not in result["annotations"][0]
    assert result["object_provenance"][0]["publisher_category_id"] == 27
    assert result["object_provenance"][0]["publisher_category_name"] == "source_image.JPG"
    assert result["categories"][0]["name"] == "CANDIDATE_VISIBLE_BLUEBERRY"
    assert result["info"]["annotation_origin"] == "UNVERIFIED"
    assert result["info"]["evidence_status"] == "PENDING_QUALITY_REVIEW"
    assert result["accuracy_status"] == "NOT_EVALUABLE_GT_QUALITY_PENDING"


def test_mpo_reference_orientation_and_extra_frames_are_not_silently_ignored() -> None:
    from io import BytesIO

    from PIL import Image

    source = Image.new("RGB", (8, 8), (30, 90, 150))
    exif = Image.Exif()
    exif[274] = 6
    oriented = BytesIO()
    source.save(oriented, format="JPEG", exif=exif)
    with pytest.raises(
        sources.SourceError, match="PUBLIC_REFERENCE_ORIENTATION_REQUIRES_GEOMETRY_ADAPTER"
    ):
        sources.normalize_public_first_frame(oriented.getvalue())
    multiple = BytesIO()
    source.save(multiple, format="MPO", save_all=True, append_images=[source] * 4)
    with pytest.raises(sources.SourceError, match="PUBLIC_IMAGE_FRAME_LIMIT"):
        sources.normalize_public_first_frame(multiple.getvalue())


def test_corrupt_public_container_has_explicit_reason_code() -> None:
    with pytest.raises(sources.SourceError, match="PUBLIC_IMAGE_DECODE_FAILED"):
        sources.normalize_public_first_frame(b"JPEG extension is not proof of decodable bytes")
