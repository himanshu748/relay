import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.schemas import (
    DemoState,
    ErrorResponse,
    EventCreate,
    HealthResponse,
)
from backend.app.services.memory import BlobSnapshotStore, INCIDENT_ID, IncidentMemory


LOCAL_DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "relay-memory.db"
DATA_PATH = Path(
    os.environ.get(
        "RELAY_DATA_PATH",
        "/tmp/relay-memory.db" if os.environ.get("VERCEL") else str(LOCAL_DATA_PATH),
    )
)


def create_app(database_path: str | Path = DATA_PATH) -> FastAPI:
    app = FastAPI(
        title="Relay Incident Memory API",
        version="0.1.0",
        description=(
            "A Sibyl Memory-backed incident response agent that changes its next action "
            "using facts and outcomes recalled from prior sessions."
        ),
    )
    snapshot_token = os.environ.get("RELAY_READ_WRITE_TOKEN")
    snapshot_store = BlobSnapshotStore(snapshot_token) if snapshot_token else None
    memory = IncidentMemory(database_path, snapshot_store=snapshot_store)
    app.state.memory = memory

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:4173",
            "http://127.0.0.1:4173",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://terminal.local:4173",
            "https://relay-incident-memory.a-9724.chatgpt.site",
        ],
        allow_origin_regex=r"https://([a-z0-9-]+\.)*(openai\.site|vercel\.app)",
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-Request-ID"],
    )

    @app.exception_handler(KeyError)
    async def not_found_handler(_, exc: KeyError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": f"Incident {exc.args[0]} was not found"},
        )

    @app.get("/api/health", response_model=HealthResponse, tags=["system"])
    def health() -> HealthResponse:
        return HealthResponse(status="ok", memory_backend=memory.backend_name)

    @app.get(
        "/api/demo",
        response_model=DemoState,
        responses={500: {"model": ErrorResponse}},
        tags=["demo"],
    )
    def get_demo() -> DemoState:
        return memory.state()

    @app.post("/api/demo/reset", response_model=DemoState, tags=["demo"])
    def reset_demo() -> DemoState:
        memory.seed()
        return memory.state()

    @app.post(
        f"/api/incidents/{INCIDENT_ID}/sessions",
        response_model=DemoState,
        tags=["incidents"],
    )
    def start_fresh_session() -> DemoState:
        return memory.state(fresh_session=True)

    @app.post(
        "/api/incidents/{incident_id}/events",
        response_model=DemoState,
        responses={404: {"model": ErrorResponse}},
        tags=["incidents"],
    )
    def add_event(incident_id: str, payload: EventCreate) -> DemoState:
        try:
            memory.add_event(incident_id, payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Incident {incident_id} was not found") from exc
        return memory.state()

    return app


app = create_app()
