from __future__ import annotations

import hashlib
import json
from typing import Any

from backend.app.baseline.schemas import SelectedBuildRun


def _stable_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def source_signature(build_runs: list[SelectedBuildRun]) -> str:
    payload = [
        {
            "season_code": item.season_code,
            "build_run_id": item.build_run_id,
            "aggregation_version": item.aggregation_version,
            "source_max_raw_id": item.source_max_raw_id,
            "config_hash": item.config_hash,
        }
        for item in sorted(build_runs, key=lambda row: (row.season_code, row.build_run_id))
    ]
    return hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()
