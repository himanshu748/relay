from backend.app.schemas import Incident, MemoryItem, Recommendation


STATELESS_RECOMMENDATION = (
    "Restart checkout-api, then watch p95 latency for five minutes."
)


def build_memory_trace(incident: Incident) -> list[MemoryItem]:
    memories: list[MemoryItem] = [
        MemoryItem(
            tier="HOT",
            label="Active incident",
            detail=f"{incident.id} remains {incident.status} with {incident.impact}",
            source="get_state(active_incident)",
        )
    ]

    if incident.hypotheses:
        hypothesis = max(incident.hypotheses, key=lambda item: item.confidence)
        memories.append(
            MemoryItem(
                tier="WARM",
                label="Leading hypothesis",
                detail=f"{hypothesis.text} ({hypothesis.confidence:.0%} confidence)",
                source=f"get_entity(incident, {incident.id})",
            )
        )

    failed = [
        attempt
        for attempt in incident.attempted_actions
        if attempt.result.lower() in {"failed", "no improvement", "blocked"}
    ]
    if failed:
        latest = failed[-1]
        memories.append(
            MemoryItem(
                tier="COLD",
                label="Failed remediation",
                detail=f"{latest.action} produced: {latest.result}",
                source="read_events()",
            )
        )

    if incident.constraints:
        memories.append(
            MemoryItem(
                tier="WARM",
                label="Operator constraint",
                detail=incident.constraints[-1],
                source=f"get_entity(incident, {incident.id})",
            )
        )

    return memories


def recommend(incident: Incident) -> Recommendation:
    attempts = " ".join(
        f"{item.action} {item.result}" for item in incident.attempted_actions
    ).lower()
    constraints = " ".join(incident.constraints).lower()
    hypotheses = " ".join(item.text for item in incident.hypotheses).lower()

    is_checkout_incident = "checkout" in f"{incident.service} {incident.title}".lower()
    if is_checkout_incident and "restart" in attempts and (
        "failed" in attempts or "no improvement" in attempts
    ):
        blocked = ["Restart checkout-api"]
        if "snapshot" in constraints or "do not restart" in constraints:
            blocked.append("Restart primary database")
        return Recommendation(
            action=(
                "Shift 20% of checkout traffic to the healthy pool and capture a "
                "connection-pool dump before changing capacity."
            ),
            rationale=(
                "A restart already failed in the prior session. The remembered database "
                "snapshot constraint rules out the usual fallback, while the leading "
                "pool-exhaustion hypothesis makes a controlled traffic shift the safest "
                "next diagnostic action."
            ),
            confidence=0.86 if "pool" in hypotheses else 0.74,
            blocked_actions=blocked,
            evidence=[
                "Prior checkout-api restart produced no improvement",
                "Primary database restart is blocked until the replica snapshot completes",
                "Connection-pool exhaustion is the leading hypothesis",
            ],
        )

    if "rollback" in attempts and "failed" in attempts:
        return Recommendation(
            action="Isolate the canary and compare its connection metrics with the stable pool.",
            rationale="The remembered rollback failure makes another rollback low-value.",
            confidence=0.78,
            blocked_actions=["Repeat the failed rollback"],
            evidence=["Rollback failed in an earlier operator session"],
        )

    failed_attempts = [
        item
        for item in incident.attempted_actions
        if any(marker in item.result.lower() for marker in ("failed", "no improvement", "blocked"))
    ]
    leading_hypothesis = (
        max(incident.hypotheses, key=lambda item: item.confidence)
        if incident.hypotheses
        else None
    )
    if failed_attempts:
        failed = failed_attempts[-1]
        next_action = (
            f"Test the leading hypothesis: {leading_hypothesis.text}."
            if leading_hypothesis
            else "Capture a new diagnostic that can separate the remaining failure modes."
        )
        evidence = [f"{failed.action} produced {failed.result}"]
        if incident.constraints:
            evidence.append(f"Operator constraint: {incident.constraints[-1]}")
        if leading_hypothesis:
            evidence.append(
                f"Leading hypothesis is {leading_hypothesis.confidence:.0%} confident"
            )
        return Recommendation(
            action=next_action,
            rationale=(
                "Relay ruled out repeating the latest ineffective action and selected "
                "a reversible diagnostic from the evidence retained across sessions."
            ),
            confidence=leading_hypothesis.confidence if leading_hypothesis else 0.66,
            blocked_actions=[f"Repeat: {failed.action}"],
            evidence=evidence,
        )

    if leading_hypothesis:
        return Recommendation(
            action=f"Run a reversible check for: {leading_hypothesis.text}.",
            rationale=(
                "This is the highest-confidence hypothesis in the incident memory. "
                "Relay recommends testing it before making an irreversible change."
            ),
            confidence=leading_hypothesis.confidence,
            blocked_actions=[],
            evidence=[f"Hypothesis confidence: {leading_hypothesis.confidence:.0%}"],
        )

    if incident.observations:
        return Recommendation(
            action="Capture a second observation that narrows the affected component or region.",
            rationale=(
                "Relay has an observed symptom but not enough evidence to prefer a "
                "remediation safely."
            ),
            confidence=0.58,
            blocked_actions=[],
            evidence=[incident.observations[-1]],
        )

    return Recommendation(
        action="Record the first observation before choosing a remediation.",
        rationale="The workspace is live, but Relay needs incident evidence to ground a safe next action.",
        confidence=0.4,
        blocked_actions=[],
        evidence=["No observations or completed remediations are recorded yet"],
    )
