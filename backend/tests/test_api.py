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


def test_anonymous_workspace_can_be_created_reopened_and_recalled(tmp_path: Path) -> None:
    app = create_app(tmp_path / "memory.db")
    client = TestClient(app)

    created = client.post(
        "/api/incidents",
        json={
            "title": "Webhook delivery delay",
            "service": "events-worker",
            "severity": "SEV-2",
            "impact": "Customers receive webhooks more than five minutes late",
        },
    )
    assert created.status_code == 201
    incident_id = created.json()["incident"]["id"]
    assert incident_id.startswith("INC-")
    assert created.json()["recommendation"]["confidence"] == 0.4

    evidence = client.post(
        f"/api/incidents/{incident_id}/events",
        json={
            "kind": "hypothesis",
            "summary": "The retry queue is saturated",
            "confidence": 0.82,
        },
    )
    assert evidence.status_code == 200
    assert "retry queue" in evidence.json()["recommendation"]["action"].lower()

    failed_action = client.post(
        f"/api/incidents/{incident_id}/events",
        json={
            "kind": "action",
            "summary": "Restarted webhook worker pool",
            "outcome": "no improvement",
        },
    )
    assert failed_action.status_code == 200
    assert "retry queue" in failed_action.json()["recommendation"]["action"].lower()
    assert "checkout traffic" not in failed_action.json()["recommendation"]["action"].lower()

    session = client.post(f"/api/incidents/{incident_id}/sessions")
    assert session.status_code == 200
    assert session.json()["is_fresh_session"] is True
    assert session.json()["session_id"].startswith("relay-")

    reopened = client.get(f"/api/incidents/{incident_id}")
    assert reopened.status_code == 200
    assert reopened.json()["session_id"] == session.json()["session_id"]
    assert reopened.json()["incident"]["title"] == "Webhook delivery delay"


def test_anonymous_workspaces_are_isolated(tmp_path: Path) -> None:
    app = create_app(tmp_path / "memory.db")
    client = TestClient(app)
    first = client.post(
        "/api/incidents",
        json={
            "title": "Search errors",
            "service": "search-api",
            "severity": "SEV-2",
            "impact": "Search returns errors for some customers",
        },
    ).json()
    second = client.post(
        "/api/incidents",
        json={
            "title": "Email delay",
            "service": "mailer",
            "severity": "SEV-3",
            "impact": "Transactional email is delayed",
        },
    ).json()

    client.post(
        f"/api/incidents/{first['incident']['id']}/events",
        json={"kind": "observation", "summary": "Errors are isolated to EU traffic"},
    )

    untouched = client.get(f"/api/incidents/{second['incident']['id']}").json()
    assert untouched["incident"]["observations"] == []
    assert all("EU traffic" not in event["summary"] for event in untouched["journal"])


def test_unknown_incident_returns_404(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "memory.db"))
    assert client.get("/api/incidents/INC-UNKNOWN").status_code == 404
    assert client.post("/api/incidents/INC-UNKNOWN/sessions").status_code == 404


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
