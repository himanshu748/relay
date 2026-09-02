from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from threading import RLock
from typing import Any, Protocol
from uuid import uuid4

from sibyl_memory_client import MemoryClient
from sibyl_memory_client.exceptions import NotFoundError
from vercel.blob import BlobClient, BlobNotFoundError

from backend.app.schemas import (
    Attempt,
    DemoState,
    EventCreate,
    Hypothesis,
    Incident,
    JournalEvent,
)
from backend.app.services.recommendation import (
    STATELESS_RECOMMENDATION,
    build_memory_trace,
    recommend,
)


TENANT_ID = "00000000-0000-0000-0000-000000000204"
INCIDENT_ID = "INC-204"


class SnapshotStore(Protocol):
    def restore(self, database_path: Path) -> bool: ...

    def persist(self, database_path: Path) -> None: ...


class BlobSnapshotStore:
    def __init__(
        self,
        token: str,
        *,
        client: Any | None = None,
        blob_path: str = "relay/sibyl-memory.db",
    ) -> None:
        self.client = client or BlobClient(token=token)
        self.blob_path = blob_path

    def restore(self, database_path: Path) -> bool:
        try:
            snapshot = self.client.get(
                self.blob_path,
                access="private",
                use_cache=False,
            )
        except BlobNotFoundError:
            return False
        restore_path = database_path.with_suffix(".restore")
        restore_path.write_bytes(snapshot.content)
        restore_path.replace(database_path)
        return True

    def persist(self, database_path: Path) -> None:
        self.client.put(
            self.blob_path,
            database_path.read_bytes(),
            access="private",
            content_type="application/vnd.sqlite3",
            overwrite=True,
        )


def repair_portable_shadow(database_path: Path) -> bool:
    """Rebuild Sibyl's derived trigram index when the host tokenizer differs."""
    with sqlite3.connect(database_path) as connection:
        try:
            connection.execute(
                "SELECT rowid FROM search_shadow "
                "WHERE search_shadow MATCH 'relay' LIMIT 1"
            ).fetchone()
            return False
        except sqlite3.OperationalError as exc:
            message = str(exc).lower()
            if not any(
                marker in message
                for marker in (
                    "error in tokenizer constructor",
                    "no such tokenizer",
                    "vtable constructor",
                )
            ):
                raise

        schema_version = connection.execute("PRAGMA schema_version").fetchone()[0]
        try:
            connection.execute("PRAGMA writable_schema = ON")
            connection.execute(
                "DELETE FROM sqlite_master "
                "WHERE type = 'trigger' AND instr(sql, 'search_shadow') > 0"
            )
            connection.execute(
                "DELETE FROM sqlite_master "
                "WHERE type = 'table' "
                "AND (name = 'search_shadow' OR name GLOB 'search_shadow_*')"
            )
            connection.execute(f"PRAGMA schema_version = {schema_version + 1}")
            connection.execute("PRAGMA user_version = 3")
            connection.commit()
        finally:
            connection.execute("PRAGMA writable_schema = OFF")
        return True


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def seed_incident() -> Incident:
    epoch = str(uuid4())
    return Incident(
        id=INCIDENT_ID,
        title="Checkout latency spike",
        service="checkout-api",
        severity="SEV-1",
        status="investigating",
        started_at="2026-08-19T13:42:00Z",
        impact="31% of checkout requests exceed 2.5 seconds",
        observations=[
            "p95 latency rose from 420 ms to 3.8 s after the 13:35 deploy",
            "Errors cluster in ap-south-1 on the primary connection pool",
        ],
        constraints=[
            "Do not restart the primary database until the replica snapshot completes at 15:20 UTC"
        ],
        attempted_actions=[
            Attempt(
                action="Restart checkout-api",
                result="no improvement",
                at="2026-08-19T14:05:00Z",
            )
        ],
        hypotheses=[
            Hypothesis(
                text="Connection-pool exhaustion after the deploy",
                confidence=0.78,
            )
        ],
        demo_epoch=epoch,
    )


class IncidentMemory:
    """Thin application adapter over Sibyl Memory's entity, state and journal tiers."""

    def __init__(
        self,
        database_path: str | Path,
        *,
        snapshot_store: SnapshotStore | None = None,
    ) -> None:
        self.path = Path(database_path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.snapshot_store = snapshot_store
        restored = False
        if self.snapshot_store:
            restored = self.snapshot_store.restore(self.path)
        if restored:
            repair_portable_shadow(self.path)
        self.client = MemoryClient.local(self.path, tenant_id=TENANT_ID)
        self.lock = RLock()
        durability = " · private durable snapshots" if self.snapshot_store else ""
        self.backend_name = f"Sibyl Memory 0.6.1 · local SQLite + FTS5{durability}"

    def persist_snapshot(self) -> None:
        if not self.snapshot_store:
            return
        with self.client.storage.connection() as connection:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.snapshot_store.persist(self.path)

    def get_incident(self, incident_id: str = INCIDENT_ID) -> Incident | None:
        with self.lock:
            try:
                entity = self.client.get_entity("incident", incident_id)
            except NotFoundError:
                return None
            if not entity:
                return None
            return Incident.model_validate(entity["body"])

    def save_incident(self, incident: Incident) -> None:
        with self.lock:
            self.client.set_entity(
                "incident",
                incident.id,
                incident.model_dump(mode="json"),
                status=incident.status,
            )
            self.client.set_state(
                "active_incident",
                {
                    "id": incident.id,
                    "severity": incident.severity,
                    "status": incident.status,
                    "impact": incident.impact,
                    "demo_epoch": incident.demo_epoch,
                },
            )

    def seed(self) -> Incident:
        with self.lock:
            incident = seed_incident()
            self.save_incident(incident)
            self.client.set_state(
                "latest_session",
                {
                    "incident": incident.id,
                    "session_id": None,
                    "memories_loaded": 0,
                    "demo_epoch": incident.demo_epoch,
                },
            )
            self.client.write_event(
                evaluated={
                    "incident": incident.id,
                    "kind": "observation",
                    "summary": incident.observations[0],
                },
                acted=["Restart checkout-api"],
                forward={"result": "no improvement"},
                extra={"demo_epoch": incident.demo_epoch},
                ts="2026-08-19T14:05:00Z",
            )
            self.persist_snapshot()
            return incident

    def ensure_seeded(self) -> Incident:
        incident = self.get_incident()
        return incident if incident else self.seed()

    def add_event(self, incident_id: str, payload: EventCreate) -> Incident:
        with self.lock:
            incident = self.get_incident(incident_id)
            if not incident:
                raise KeyError(incident_id)

            timestamp = utc_now()
            if payload.kind == "observation":
                incident.observations.append(payload.summary)
            elif payload.kind == "constraint":
                incident.constraints.append(payload.summary)
            elif payload.kind == "action":
                incident.attempted_actions.append(
                    Attempt(
                        action=payload.summary,
                        result=payload.outcome or "completed",
                        at=timestamp,
                    )
                )
            elif payload.kind == "hypothesis":
                incident.hypotheses.append(
                    Hypothesis(
                        text=payload.summary,
                        confidence=payload.confidence if payload.confidence is not None else 0.5,
                    )
                )

            self.save_incident(incident)
            current_recommendation = recommend(incident)
            self.client.write_event(
                evaluated={
                    "incident": incident.id,
                    "kind": payload.kind,
                    "summary": payload.summary,
                },
                acted=[payload.summary] if payload.kind == "action" else None,
                forward={
                    "outcome": payload.outcome,
                    "next_action": current_recommendation.action,
                },
                extra={"demo_epoch": incident.demo_epoch},
                ts=timestamp,
            )
            self.persist_snapshot()
            return incident

    def journal(self, incident: Incident) -> list[JournalEvent]:
        with self.lock:
            rows = self.client.read_events(limit=100)

        events: list[JournalEvent] = []
        for row in rows:
            evaluated = row.get("evaluated") or {}
            extra = row.get("extra") or {}
            if evaluated.get("incident") != incident.id:
                continue
            if extra.get("demo_epoch") != incident.demo_epoch:
                continue
            forward = row.get("forward") or {}
            events.append(
                JournalEvent(
                    id=row["id"],
                    timestamp=row["ts"],
                    kind=evaluated.get("kind", "event"),
                    summary=evaluated.get("summary", "Incident memory updated"),
                    outcome=forward.get("outcome") or forward.get("result"),
                )
            )
        return sorted(events, key=lambda event: event.timestamp, reverse=True)

    def start_fresh_session(self, incident: Incident) -> str:
        session_id = f"relay-{uuid4().hex[:8]}"
        memory_trace = build_memory_trace(incident)
        recommendation = recommend(incident)
        started_at = utc_now()
        with self.lock:
            self.client.set_state(
                f"session:{session_id}",
                {
                    "incident": incident.id,
                    "started_at": started_at,
                    "memories_loaded": len(memory_trace),
                },
            )
            self.client.set_state(
                "latest_session",
                {
                    "incident": incident.id,
                    "session_id": session_id,
                    "started_at": started_at,
                    "memories_loaded": len(memory_trace),
                    "demo_epoch": incident.demo_epoch,
                },
            )
            self.client.write_event(
                evaluated={
                    "incident": incident.id,
                    "kind": "fresh_session",
                    "summary": f"Loaded {len(memory_trace)} memories into {session_id}",
                },
                forward={"next_action": recommendation.action},
                extra={"demo_epoch": incident.demo_epoch},
            )
            self.persist_snapshot()
        return session_id

    def latest_session_id(self, incident: Incident) -> str | None:
        with self.lock:
            try:
                state = self.client.get_state("latest_session")
            except NotFoundError:
                return None
        body = (state or {}).get("body") or {}
        if body.get("incident") != incident.id or body.get("demo_epoch") != incident.demo_epoch:
            return None
        session_id = body.get("session_id")
        return session_id if isinstance(session_id, str) and session_id else None

    def state(self, *, fresh_session: bool = False) -> DemoState:
        incident = self.ensure_seeded()
        if fresh_session:
            session_id = self.start_fresh_session(incident)
        else:
            session_id = self.latest_session_id(incident) or "relay-live"
        has_session_receipt = session_id != "relay-live"
        return DemoState(
            incident=incident,
            recommendation=recommend(incident),
            stateless_recommendation=STATELESS_RECOMMENDATION,
            memories=build_memory_trace(incident),
            journal=self.journal(incident),
            session_id=session_id,
            memory_backend=self.backend_name,
            is_fresh_session=has_session_receipt,
        )
