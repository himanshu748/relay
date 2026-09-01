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

    if "restart" in attempts and (
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

    return Recommendation(
        action="Capture a connection-pool dump, then validate saturation by availability zone.",
        rationale="Relay has not yet observed a failed remediation, so it starts with a reversible diagnostic.",
        confidence=0.62,
        blocked_actions=[],
        evidence=["Checkout latency is elevated", "No completed remediation is recorded"],
    )

