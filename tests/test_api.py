from __future__ import annotations

from fastapi.testclient import TestClient

from gpt_register_bot.interfaces.web.main import create_app


def test_health_endpoints() -> None:
    app = create_app()
    client = TestClient(app)

    index = client.get("/")
    assert index.status_code == 200

    state = client.get("/api/state")
    assert state.status_code == 200
    payload = state.json()
    assert payload["running"] is False
    assert isinstance(payload["logs"], list)
