"""GET /agents/state must stay shape-identical to docs/api_stub.json.

The dashboard is being built against the stub. If the live endpoint drifts from it -- a key
renamed, a number turned into a string -- the dashboard breaks on the day it swaps in.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app as score_app
from app import AgentsStateResponse, app

STUB_PATH = Path(__file__).resolve().parents[2] / "docs" / "api_stub.json"
STUB = json.loads(STUB_PATH.read_text())

client = TestClient(app)


def _published_from_stub() -> dict:
    """The raw snapshot the oracle would push to produce the stub's agents."""
    return {
        "chain_id": STUB["chain_id"],
        "block": STUB["block"],
        "agents": [
            {
                "address": agent["address"],
                "name": agent["name"],
                "score": agent["score"],
                "previous_score": agent["previous_score"],
                "top_factors": agent["top_factors"],
                "recent_events": agent["recent_events"],
            }
            for agent in STUB["agents"]
        ],
    }


@pytest.fixture(autouse=True)
def _empty_oracle_state():
    score_app.ORACLE_STATE.snapshot = None
    score_app.ORACLE_STATE.received_at = None
    score_app.ORACLE_STATE.received_monotonic = 0.0
    yield


def _kind(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "number"  # JSON has one number type; 500 and 500.0 are the same to a dashboard
    return type(value).__name__


def assert_same_shape(live, stub, path: str = "$") -> None:
    """Same keys at every level, same JSON type at every leaf. Null matches either side, since
    a nullable field (job_id, notice) is legitimately null in one and set in the other."""
    if live is None or stub is None:
        return
    assert _kind(live) == _kind(stub), f"{path}: live is {_kind(live)}, stub is {_kind(stub)}"

    if isinstance(stub, dict):
        assert set(live) == set(stub), (
            f"{path}: keys differ. only live: {sorted(set(live) - set(stub))}, "
            f"only stub: {sorted(set(stub) - set(live))}"
        )
        for key in stub:
            assert_same_shape(live[key], stub[key], f"{path}.{key}")
    elif isinstance(stub, list):
        assert live and stub, f"{path}: need a non-empty list on both sides to compare"
        for i, item in enumerate(live):
            assert_same_shape(item, stub[0], f"{path}[{i}]")
        for i, item in enumerate(stub):
            assert_same_shape(live[0], item, f"{path}[{i}] (stub)")


def test_stub_is_a_valid_response():
    AgentsStateResponse.model_validate(STUB)


def test_live_endpoint_has_the_stubs_shape():
    assert client.put("/internal/agents/state", json=_published_from_stub()).status_code == 204

    live = client.get("/agents/state").json()

    assert live["source"] == "oracle"
    assert_same_shape(live, STUB)


def test_live_endpoint_derives_the_stubs_numbers():
    """Band, collateral and deltas are computed server-side and must match the stub exactly."""
    client.put("/internal/agents/state", json=_published_from_stub())

    live = client.get("/agents/state").json()

    assert live["agents"] == STUB["agents"]


def test_sloppy_agent_crosses_two_tiers():
    client.put("/internal/agents/state", json=_published_from_stub())
    sloppy = next(a for a in client.get("/agents/state").json()["agents"] if a["name"] == "SloppyAgent")

    assert (sloppy["previous_band"], sloppy["band"]) == ("good", "poor")
    assert (sloppy["previous_required_collateral_pct"], sloppy["required_collateral_pct"]) == ("40%", "100%")
    assert sloppy["score_delta"] == -231


def test_before_the_oracle_reports_the_response_says_so():
    body = client.get("/agents/state").json()

    assert body["agents"] == []
    assert body["oracle_live"] is False
    assert "oracle" in body["notice"]
    AgentsStateResponse.model_validate(body)


def test_a_silent_oracle_is_flagged_stale():
    client.put("/internal/agents/state", json=_published_from_stub())
    score_app.ORACLE_STATE.received_monotonic -= score_app.ORACLE_STALE_SECONDS + 1

    body = client.get("/agents/state").json()

    assert body["oracle_live"] is False
    assert body["notice"]
    assert len(body["agents"]) == 3


def test_unknown_fields_from_the_oracle_are_rejected():
    snapshot = _published_from_stub()
    snapshot["agents"][0]["band"] = "excellent"  # derived here, never accepted from outside

    assert client.put("/internal/agents/state", json=snapshot).status_code == 422
