# Relay architecture

## Runtime flow

```text
Responder action
      |
      v
React incident console
      |
      v
FastAPI application
      |
      +--> incident entity ----------> WARM memory
      +--> active incident ----------> HOT state
      +--> latest session receipt ---> HOT state
      +--> evidence and outcomes ----> COLD event journal
      |
      +--> SQLite checkpoint --------> private Vercel Blob
      |                                  |
      |<--------- cold-start restore ----+
      |
      v
Recommendation engine
      |
      +--> proposed action
      +--> blocked actions
      +--> visible evidence trace
```

## Memory model

The durable incident entity is the source for observations, attempted actions, constraints and ranked hypotheses. The HOT active state allows a new responder to regain working context immediately. Each evidence write and fresh-session recall is also written to the COLD journal with a `demo_epoch`, so reset creates a clean demo without deleting historical rows.

The real-world validation uses a separate `validation` entity and `validation:GH-ACTIONS-2026-08-26` state key. It never mutates the checkout demo. Each run creates a new session and four COLD journal events, while the first deployment fingerprint stays attached to the receipt so a later deployment can prove that it restored the same durable memory.

Sibyl remains the memory engine and SQLite remains its source of truth. The production adapter checkpoints that database after mutations, uploads it to a private Vercel Blob and restores it before opening Sibyl on a cold start. A compatibility repair rebuilds only Sibyl's derived FTS shadow index when the deployment runtime uses a different SQLite tokenizer, leaving HOT, WARM and COLD rows intact.

`build_memory_trace()` turns the raw memory into four explicit items. `recommend()` consumes the incident and returns the action, confidence, blocked actions and three evidence statements. The UI renders those fields without inventing an extra explanation layer.

## API surface

- `GET /api/health`: confirms the real Sibyl backend
- `GET /api/demo`: loads the current incident and latest session receipt
- `POST /api/demo/reset`: seeds a new clean incident epoch
- `POST /api/incidents/INC-204/sessions`: starts a new responder session and records recall
- `POST /api/incidents/{incident_id}/events`: persists live evidence and recomputes the decision
- `GET /api/validations/github-actions`: reads the latest isolated real-incident receipt
- `POST /api/validations/github-actions`: writes and recalls the four sourced facts in a fresh session

## Deliberate hackathon constraints

The recommendation engine is deterministic so judges can see and reproduce the causal effect of memory without requiring an external model key. The integration boundary is narrow enough to replace with an LLM planner later while keeping the same Sibyl-backed evidence model.
