"""Offline S2 evidence bindings do not replace current PostgreSQL/ASGI tests."""

import hashlib
import json
from pathlib import Path

from backend.app.business_access.schemas import Filters
from backend.app.local_auth.repository import BUSINESS_ACCESS
from backend.tests.historical_source import historical_bytes

ROOT = Path(__file__).resolve().parents[3]
BASE = "9b894b66a018c78de11bf01de4cc1daa3408db40"
EVIDENCE = ROOT / "docs/v0-18/evidence/s2-authorized-saved-run-discovery-r1.json"
MERGED_S2 = "3410dd4426618a7a4b29c08cbf58aaef20196939"
S3_REVISED_TEST_SOURCES = {
    "backend/app/api/business_access.py",
    "backend/tests/local_auth/test_runtime_evidence_contract.py",
    "backend/tests/business_access/test_contract.py",
}


def test_canonical_sources_frozen_history_and_governance():
    raw = EVIDENCE.read_bytes()
    value = json.loads(raw)
    assert raw == (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    assert value["base_main_sha"] == BASE
    assert value["task_id"] == "V0_18_S2_AUTHORIZED_SAVED_RUN_DISCOVERY_AND_HANDOFF_R1"
    for relative, expected in value["source_evidence_sha256"].items():
        path = Path(relative)
        assert not path.is_absolute() and ".." not in path.parts
        source = (
            historical_bytes(relative, MERGED_S2)
            if relative in S3_REVISED_TEST_SOURCES
            else (ROOT / path).read_bytes()
        )
        assert hashlib.sha256(source).hexdigest() == expected
    for relative, expected in value["frozen_sources_sha256"].items():
        source = (ROOT / relative).read_bytes()
        assert source == historical_bytes(relative, BASE)
        assert hashlib.sha256(source).hexdigest() == expected
    for key in (
        "production_database_changed",
        "production_deployed",
        "ready_authorized",
        "merge_authorized",
        "s2_formal_complete",
        "s3_s6_authorized",
    ):
        assert value["governance"][key] is False
    assert value["owner_s2_implementation_authorized"] is True
    assert value["runtime"]["authorization_filter_before_pagination"] is True
    assert value["runtime"]["handoff_is_bearer_authorization"] is False
    assert value["runtime"]["new_tables_migrations_dependencies"] is False
    assert value["runtime"]["client_business_math"] is False
    assert value["ci"]["result"] == "PENDING_AT_COMMIT_EXACT_HEAD_RECEIPT_REQUIRED"


def test_exact_three_ingress_and_fixed_pagination_contract():
    assert BUSINESS_ACCESS == {
        "/api/v1/business-access/" + n for n in ("scope", "saved-runs", "selection")
    }
    value = json.loads(EVIDENCE.read_text())
    assert value["runtime"]["cursor_ttl_seconds"] == 900
    assert value["runtime"]["cursor_max_bytes"] == 2048
    assert value["runtime"]["handoff_ttl_seconds"] == 300
    assert value["runtime"]["sort"] == [
        "origin_date DESC",
        "source_kind ASC",
        "forecast_family ASC",
        "run_id DESC",
        "entity_id ASC",
        "source_result_hash ASC",
    ]
    assert Filters().page_size == 20
    assert Filters(page_size=100).page_size == 100
