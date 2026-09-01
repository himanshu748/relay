# Relay

Relay is a memory-backed incident response agent built for the Sibyl Labs Hackathon. It carries operational evidence across agent sessions, recalls failed actions and operator constraints then shows exactly why its next recommendation changed.

The included demo follows `INC-204`, a checkout latency spike. A stateless responder repeats a failed service restart. Relay recalls that the restart already failed, a database restart is blocked and connection-pool exhaustion is the leading hypothesis. It recommends a controlled traffic shift plus a connection-pool dump instead.

## Why this needs Sibyl Memory

The memory is load-bearing, not decorative:

- WARM entity memory stores the durable incident record, hypotheses, constraints and attempted actions
- HOT state stores the active incident plus fresh-session receipts
- COLD events keep the auditable incident journal
- Each fresh session rebuilds the recommendation from recalled memory
- The UI places the stateless action beside the memory-backed action so the behavioral difference is visible

Relay uses the real [`sibyl-memory-client`](https://docs.sibyllabs.org/memory/integrations) local backend with SQLite and FTS5.

## How memory made this possible

Relay cannot produce its core recommendation after deleting the Sibyl Memory layer. The fresh responder would lose the failed restart, the database snapshot constraint and the leading hypothesis, then fall back to the stateless restart action. Sibyl is therefore on the critical path for the product's decision, not a logging sidecar.

The write and read paths are easy to audit:

- `backend/app/services/memory.py::add_event` persists new evidence to the incident entity and COLD journal
- `backend/app/services/memory.py::start_fresh_session` records the new session and its recall receipt
- `backend/app/services/memory.py::state` rebuilds the current state from Sibyl on every request
- `backend/app/services/recommendation.py::build_memory_trace` turns recalled state into the visible decision trace

## Partner stacks

No Base or Virtuals multiplier is claimed in the current build. Relay uses Sibyl Memory only.

## Prior Work declaration

The first Relay prototype was created on August 19, 2026 before the official September 1 to 10 build window. This repository will preserve that history and disclose all pre-window work. Material changes made during the event will remain visible in the public commit history.

## Run locally

Requirements: Python 3.12+, Node.js 20+ and npm.

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
.venv/bin/uvicorn backend.app.main:app --host 127.0.0.1 --port 8787
```

In a second terminal:

```bash
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 4173 --strictPort
```

Open [http://127.0.0.1:4173](http://127.0.0.1:4173). API documentation is available at [http://127.0.0.1:8787/docs](http://127.0.0.1:8787/docs).

## Local walkthrough, 75 seconds

1. Start with the hero claim, then show the stateless restart beside Relay recall.
2. Read the three evidence rows. They explain what failure, constraint and hypothesis survive the handoff.
3. Select **Run the memory test**. Relay creates a new session, recalls four memories and opens the Receipt view.
4. Move through Incident, Memory and Receipt to show the journal, tiers and fresh session identifier.
5. Add a live observation in the evidence form and save it.
6. Point to the new journal event and the preserved receipt.
7. Select **Reset incident** to restore the clean starting state.

The official 2 to 5 minute submission recording plan is in `docs/demo-script.md`.

## Tests

```bash
.venv/bin/pytest -q
cd frontend
npm run build
npm run test:sites
```

## Project map

- `backend/app/services/memory.py`: Sibyl Memory adapter, seeding, retrieval and journal writes
- `backend/app/services/recommendation.py`: deterministic recommendation logic that exposes memory influence
- `backend/app/main.py`: FastAPI routes
- `frontend/src/App.jsx`: interaction and evidence UI
- `frontend/src/styles.css`: responsive landing page and incident console
- `docs/architecture.md`: data flow and memory-tier mapping
- `docs/demo-script.md`: spoken hackathon walkthrough
- `docs/design-review.md`: rendered QA and improvement loop

## License

MIT, see `LICENSE`.
