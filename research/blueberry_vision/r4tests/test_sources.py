from typing import Any

import pytest

from research.blueberry_vision.r4.sources import source_admission


@pytest.mark.parametrize("license_id", ["CC0-1.0", "CC-BY-2.0", "CC-BY-4.0", "CC-BY-SA-4.0"])
def test_verified_research_sources(license_id: Any) -> None:
    assert source_admission(
        {"license_id": license_id, "license_status": "LICENSE_VERIFIED", "research_use": True}
    )["eligible"]


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"license_id": "CC-BY-NC-4.0"}, "COMPANY_NONCOMMERCIAL_SCOPE_UNRESOLVED"),
        ({"license_status": "LICENSE_UNVERIFIED"}, "LICENSE_UNVERIFIED"),
        ({"research_use": False}, "RESEARCH_USE_NOT_AUTHORIZED"),
        ({"license_id": "UNKNOWN"}, "LICENSE_SCOPE_NOT_SUPPORTED"),
    ],
)
def test_company_research_not_automatically_noncommercial(change: Any, reason: Any) -> None:
    source = {
        "license_id": "CC-BY-4.0",
        "license_status": "LICENSE_VERIFIED",
        "research_use": True,
        **change,
    }
    assert reason in source_admission(source)["reason_codes"]


def test_manual_claim_not_qualified_reference() -> None:
    report = source_admission(
        {
            "license_id": "CC-BY-4.0",
            "license_status": "LICENSE_VERIFIED",
            "research_use": True,
            "annotation_origin": "manual",
        }
    )
    assert report["qualified_gt"] is False
