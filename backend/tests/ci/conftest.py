"""An explicitly unapproved Owner decision for authorization-negative tests."""

import hashlib
import json

import pytest

from backend.app.core import historical_code_identity as identity


@pytest.fixture
def unapproved_owner_baseline(tmp_path, monkeypatch):
    # The same synthetic trust-anchor seam used by the existing catalog tests.
    # Pending decisions must still deny the exact 28 identities after approval.
    record = json.loads(identity.OWNER_DECISION_FILE.read_bytes())
    record["owner_status"] = "PENDING"
    file = tmp_path / "pending-owner-decision.json"
    file.write_text(json.dumps(record))
    monkeypatch.setattr(identity, "OWNER_DECISION_FILE", file)
    monkeypatch.setattr(
        identity, "OWNER_DECISION_SHA256", hashlib.sha256(file.read_bytes()).hexdigest()
    )
