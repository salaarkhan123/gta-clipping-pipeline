"""Live clipping HTTP surface: flag-off 404; scaffold when LIVE_CLIPPING=true."""
import os

import pytest


@pytest.fixture
def live_on(monkeypatch):
    monkeypatch.setenv("LIVE_CLIPPING", "true")
    yield
    monkeypatch.delenv("LIVE_CLIPPING", raising=False)


def test_status_public_when_flag_off(client):
    # Default test env does not set LIVE_CLIPPING → off.
    os.environ.pop("LIVE_CLIPPING", None)
    r = client.get("/v1/live/status")
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is False
    assert body["measured_realtime"] is False


def test_session_create_404_when_flag_off(client, user):
    os.environ.pop("LIVE_CLIPPING", None)
    headers, _ = user
    r = client.post("/v1/live/sessions", headers=headers,
                    json={"rights_confirmed": True, "max_minutes": 30})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "live_clipping_off"


def test_options_omits_live_when_off(client):
    os.environ.pop("LIVE_CLIPPING", None)
    r = client.get("/v1/options")
    assert r.status_code == 200
    assert "live_clipping" not in r.json()


def test_scaffold_session_and_mock_when_flag_on(client, user, live_on):
    headers, _ = user
    st = client.get("/v1/live/status")
    assert st.status_code == 200 and st.json()["enabled"] is True

    bad = client.post("/v1/live/sessions", headers=headers, json={"rights_confirmed": False})
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "rights_required"

    created = client.post("/v1/live/sessions", headers=headers,
                          json={"rights_confirmed": True, "max_minutes": 30, "mode": "mock"})
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["state"] == "LIVE"
    assert body["measured_realtime"] is False
    assert body["ingest"]["status"] == "scaffold"
    sid = body["id"]

    seg = client.post(f"/v1/live/sessions/{sid}/segments", headers=headers,
                      json={"start_sec": 0.0, "duration_sec": 2.0, "rms_db": [-40.0, -40.0]})
    assert seg.status_code == 200
    assert seg.json()["segment"]["index"] == 0

    mock = client.post(f"/v1/live/sessions/{sid}/mock", headers=headers)
    assert mock.status_code == 200, mock.text
    m = mock.json()
    assert m["tool"] == "live_clip"
    assert m["candidates"]
    assert m["timings_ms"]["total_wall_ms"] >= 0
    assert any("not a measured" in n for n in m["notes"])

    got = client.get(f"/v1/live/sessions/{sid}", headers=headers)
    assert got.status_code == 200
    assert got.json()["candidates"]

    opts = client.get("/v1/options")
    assert opts.status_code == 200
    assert opts.json()["live_clipping"]["mode"] == "scaffold"


def test_one_shot_mock_requires_auth_and_flag(client, user, live_on):
    headers, _ = user
    r = client.post("/v1/live/mock", headers=headers)
    assert r.status_code == 200
    assert r.json()["mode"] == "mock"
