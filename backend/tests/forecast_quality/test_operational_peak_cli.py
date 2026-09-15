"""CLI transport coverage for the persisted S6 operational peak product."""

from __future__ import annotations

import io
import json

from backend.app.cli import run_cli


def _body() -> dict[str, str]:
    return {
        "base_id": "base-yangliu",
        "target_season": "2026-2027",
        "origin_date": "2027-03-31",
    }


def _run(factory, words: list[str], body: dict[str, str] | None = None) -> dict:
    stdout, stderr = io.StringIO(), io.StringIO()
    code = run_cli(
        ["operational-peak-run", *words],
        session_factory=factory,
        stdin=io.StringIO(json.dumps(body) if body is not None else ""),
        stdout=stdout,
        stderr=stderr,
    )
    assert code == 0, stderr.getvalue()
    return json.loads(stdout.getvalue())


async def test_operational_peak_cli_create_get_list_daily_parity(s6_factory, s6_authority):
    created = _run(s6_factory, ["create", "--input", "-"], _body())
    run_id = created["run"]["run_id"]
    assert created["result"]["forecast_7d"]["total_kg"] == "2758.000000"
    assert created["result"]["forecast_15d"]["total_kg"] == "5910.000000"

    reused = _run(s6_factory, ["create", "--input", "-"], _body())
    assert reused["reused_existing_run"] is True
    assert reused["run"]["run_id"] == run_id

    loaded = _run(s6_factory, ["get", "--run-id", str(run_id)])
    history = _run(s6_factory, ["list"])
    daily = _run(s6_factory, ["daily", "--run-id", str(run_id)])
    assert loaded == created
    assert history["items"][0]["run_id"] == run_id
    assert len(daily["daily_forecast"]) == 15
