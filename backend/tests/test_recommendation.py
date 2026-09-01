from backend.app.services.memory import seed_incident
from backend.app.services.recommendation import STATELESS_RECOMMENDATION, recommend


def test_memory_changes_the_recommendation() -> None:
    incident = seed_incident()
    result = recommend(incident)

    assert "Restart checkout-api" in STATELESS_RECOMMENDATION
    assert "Shift 20%" in result.action
    assert "Restart checkout-api" in result.blocked_actions
    assert "snapshot" in result.rationale


def test_recommendation_has_visible_evidence() -> None:
    result = recommend(seed_incident())

    assert result.confidence >= 0.8
    assert len(result.evidence) == 3

