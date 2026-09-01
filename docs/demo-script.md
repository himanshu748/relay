# Relay submission video script

Target length: 2 minutes 40 seconds. Record the browser at 1080p. Keep the fresh-session segment continuous and unedited. Show an on-screen UTC clock or the current commit hash during that segment.

## 0:00 to 0:20, hook

"A production incident can outlive the agent session investigating it. When the next responder starts cold, it repeats failed work and ignores constraints the last responder already discovered. Relay gives incident response operational memory."

Show the hero console, active incident and grounded recommendation.

## 0:20 to 0:45, product

"Relay is a memory-backed incident response agent. It carries observations, attempted actions, hypotheses and operator constraints across sessions. More importantly, it shows which recalled memories changed the next decision."

Point to the contrast panels and the three open evidence rows.

## 0:45 to 1:15, prove behavior changed

"A stateless responder proposes restarting checkout-api. That action already failed. Relay recalls the failed restart, the database snapshot constraint and the pool-exhaustion hypothesis. It chooses a controlled traffic shift and a pool dump instead."

Point to the comparison, blocked actions and three evidence rows.

## 1:15 to 1:50, continuous fresh-session recall

Keep the on-screen clock or commit hash visible. Do not cut this section.

Select **Run the memory test**.

"This is a genuinely fresh responder session. Before choosing an action, it reads the durable incident entity, active HOT state and COLD event history from Sibyl. Four memories are recalled into a new session receipt. The recommendation remains safe because the earlier failure and constraint survived the session boundary."

Move through Incident, Memory and Receipt. Show the new session identifier, HOT, WARM and COLD items plus the journal entry.

## 1:50 to 2:15, prove live writes

In **Add live evidence**, enter: `Pool wait time is isolated to the primary zone`.

"The responder can write new operational evidence during the incident. Relay updates the incident entity, writes an auditable event and recomputes its recommendation."

Open **Incident** and point to the newest journal item, then open **Receipt** to show continuity.

## 2:15 to 2:32, technical proof

Briefly show `backend/app/services/memory.py`.

"Sibyl is on the critical path. Remove these reads and Relay loses the failure, constraint and hypothesis, then falls back to the unsafe restart. The local backend uses Sibyl Memory with SQLite and FTS5, while the API tests verify recall plus receipt continuity."

## 2:32 to 2:40, close

"Relay turns incident response from session-bound chat into cumulative operational judgment. The next responder starts where the last one stopped."
