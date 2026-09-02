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


def test_real_incident_validation_uses_isolated_sibyl_memory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("VERCEL_URL", "relay-validation-a.vercel.app")
    app = create_app(tmp_path / "memory.db")
    client = TestClient(app)

    response = client.post("/api/validations/github-actions")

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_name"] == "GitHub Status"
    assert payload["source_url"] == (
        "https://www.githubstatus.com/incidents/y1t7p9fzrlj2"
    )
    assert payload["facts_stored"] == 4
    assert payload["facts_recalled"] == 4
    assert payload["journal_events"] == 4
    assert payload["session_id"].startswith("relay-real-")
    assert payload["survived_redeploy"] is False
    assert payload["tiers"] == ["HOT", "WARM", "COLD"]
    assert any(
        fact["kind"] == "action" and "failover" in fact["summary"].lower()
        for fact in payload["facts"]
    )

    demo = client.get("/api/demo").json()
    assert all(
        "GitHub Actions" not in observation
        for observation in demo["incident"]["observations"]
    )


def test_real_incident_validation_reports_cross_deploy_restore(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "memory.db"
    monkeypatch.setenv("VERCEL_URL", "relay-validation-a.vercel.app")
    first_client = TestClient(create_app(database_path))
    first_client.post("/api/validations/github-actions")

    monkeypatch.setenv("VERCEL_URL", "relay-validation-b.vercel.app")
    second_client = TestClient(create_app(database_path))
    response = second_client.get("/api/validations/github-actions")

    assert response.status_code == 200
    payload = response.json()
    assert payload["survived_redeploy"] is True
    assert payload["facts_recalled"] == 4
    assert payload["journal_events"] == 4
