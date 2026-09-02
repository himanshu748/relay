from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import create_app


def test_public_demo_origin_is_allowed_by_cors(tmp_path: Path) -> None:
    app = create_app(tmp_path / "memory.db")
    client = TestClient(app)

    response = client.options(
        "/api/demo",
        headers={
            "Origin": "https://relay-incident-memory.a-9724.chatgpt.site",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == (
        "https://relay-incident-memory.a-9724.chatgpt.site"
    )


def test_fresh_session_recalls_prior_work(tmp_path: Path) -> None:
    app = create_app(tmp_path / "memory.db")
    client = TestClient(app)

    initial = client.get("/api/demo")
    assert initial.status_code == 200
    assert initial.json()["memory_backend"].startswith("Sibyl Memory")

    response = client.post("/api/incidents/INC-204/sessions")
    assert response.status_code == 200
    payload = response.json()
    assert payload["is_fresh_session"] is True
    assert payload["session_id"].startswith("relay-")
    assert len(payload["memories"]) >= 3
    assert payload["stateless_recommendation"] != payload["recommendation"]["action"]


def test_new_observation_is_persisted(tmp_path: Path) -> None:
    app = create_app(tmp_path / "memory.db")
    client = TestClient(app)
    client.get("/api/demo")

    response = client.post(
        "/api/incidents/INC-204/events",
        json={
            "kind": "observation",
            "summary": "Pool wait time is isolated to ap-south-1a",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert "Pool wait time is isolated to ap-south-1a" in payload["incident"]["observations"]
    assert payload["journal"][0]["kind"] == "observation"


def test_fresh_session_receipt_survives_later_writes(tmp_path: Path) -> None:
    app = create_app(tmp_path / "memory.db")
    client = TestClient(app)
    client.get("/api/demo")
    session = client.post("/api/incidents/INC-204/sessions").json()

    response = client.post(
        "/api/incidents/INC-204/events",
        json={
            "kind": "observation",
            "summary": "Pool wait time is isolated to ap-south-1a",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["is_fresh_session"] is True
    assert payload["session_id"] == session["session_id"]
