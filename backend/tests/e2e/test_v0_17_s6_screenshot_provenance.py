"""Offline archive admission regression; no browser or business calculation."""

import base64
import copy
import hashlib
import json
import runpy
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.contract]
collect = runpy.run_path(str(Path(__file__).with_name("build_v0_17_s6_evidence.py")))[
    "collect_screenshots"
]


def report(tmp_path):
    specs = []
    for index in range(44):
        name = f"sample-{index}-SYNTHETIC.png"
        path = tmp_path / str(index) / name
        path.parent.mkdir()
        path.write_bytes(b"SYNTHETIC_TEST_IMAGE")
        meta = {
            "execution_id": "fresh-test-run",
            "test_file": "e2e/dashboard-cross-surface.spec.ts",
            "test_id": f"spec-{index}",
            "test_title": f"case-{index}",
            "project": "chromium-desktop",
            "captured_at": "2026-10-08T15:00:01Z",
            "name": name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        specs.append(
            {
                "id": f"spec-{index}",
                "file": "dashboard-cross-surface.spec.ts",
                "title": meta["test_title"],
                "tests": [
                    {
                        "projectName": "chromium-desktop",
                        "status": "expected",
                        "results": [
                            {
                                "status": "passed",
                                "retry": 0,
                                "startTime": "2026-10-08T15:00:00Z",
                                "duration": 2000,
                                "attachments": [
                                    {"name": name, "contentType": "image/png", "path": str(path)},
                                    {
                                        "name": "provenance:" + name,
                                        "contentType": "application/json",
                                        "body": base64.b64encode(
                                            json.dumps(meta).encode()
                                        ).decode(),
                                    },
                                ],
                            }
                        ],
                    }
                ],
            }
        )
    return {
        "stats": {"startTime": "2026-10-08T15:00:00Z", "duration": 2000},
        "suites": [{"specs": specs}],
    }


def test_exact_report_attachments_ignore_unrelated_disk_files(tmp_path):
    value = report(tmp_path)
    (tmp_path / "cancel-reopen-SYNTHETIC.png").write_bytes(b"STALE_UNRELATED")
    assert len(collect(value, "fresh-test-run", tmp_path)) == 44


def test_duplicate_destination_fails_before_any_archive_copy(tmp_path):
    value = report(tmp_path)
    duplicate = copy.deepcopy(value["suites"][0]["specs"][0])
    image = duplicate["tests"][0]["results"][0]["attachments"][0]
    path = tmp_path / "other-test" / image["name"]
    path.parent.mkdir()
    path.write_bytes(b"SYNTHETIC_TEST_IMAGE")
    image["path"] = str(path)
    duplicate["id"] = "different-test-id"
    duplicate["title"] = "different case same screenshot basename"
    attachment = duplicate["tests"][0]["results"][0]["attachments"][1]
    meta = json.loads(base64.b64decode(attachment["body"]))
    meta.update(test_id=duplicate["id"], test_title=duplicate["title"])
    attachment["body"] = base64.b64encode(json.dumps(meta).encode()).decode()
    value["suites"][0]["specs"].append(duplicate)
    with pytest.raises(AssertionError, match="DUPLICATE_DESTINATION"):
        collect(value, "fresh-test-run", tmp_path)


@pytest.mark.parametrize(
    "fault",
    ["stale", "unrelated", "missing", "tampered", "outside", "test_id", "project", "timestamp"],
)
def test_unattributable_sources_fail_closed(tmp_path, fault):
    value = report(tmp_path)
    spec = value["suites"][0]["specs"][0]
    attachments = spec["tests"][0]["results"][0]["attachments"]
    if fault == "unrelated":
        spec["file"] = "selector-cancel-reopen.spec.ts"
    elif fault == "missing":
        attachments.pop()
    elif fault == "tampered":
        Path(attachments[0]["path"]).write_bytes(b"CHANGED")
    elif fault == "outside":
        attachments[0]["path"] = str(tmp_path.parent / "outside.png")
    elif fault in ("test_id", "project", "timestamp"):
        meta = json.loads(base64.b64decode(attachments[1]["body"]))
        meta[{"test_id": "test_id", "project": "project", "timestamp": "captured_at"}[fault]] = {
            "test_id": "another-test",
            "project": "chromium-mobile",
            "timestamp": "2025-01-01T00:00:00Z",
        }[fault]
        attachments[1]["body"] = base64.b64encode(json.dumps(meta).encode()).decode()
    with pytest.raises((AssertionError, ValueError)):
        collect(value, "wrong-run" if fault == "stale" else "fresh-test-run", tmp_path)
