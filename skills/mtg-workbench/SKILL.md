---
name: mtg-workbench
description: Serve the deck workbench agent bridge — poll /api/agent/next on the local hub (deck_workbench.py, port 8644), answer the four request kinds (next_move / explain / novel_synergies / handoff) with kernel evidence, and write candidates back as avenues. Use when the user asks the agent to connect to the workbench, or while a workbench page request is pending.
---

# MTG Workbench Agent Bridge

The workbench hub (`tools/deck_workbench.py serve`, default `127.0.0.1:8644`)
holds one authoritative deck state with a browser page on one side and this
agent session on the other. The page's judgment requests reach you through the
bridge; deterministic compute never does — do not re-do what the kernel already
shows in the snapshot.

The browser's **Connect** button (labelled with the active backend) starts the
persistent receiver in `tools/workbench_agent.py`. The receiver core is
backend-agnostic (claim loop, lease heartbeats, page approvals, receipts);
the actual Agent CLI is a registered adapter — currently `codex`
(`tools/workbench_agent_codex.py`, driving the installed CLI's
`codex app-server` JSONL protocol), with more backends able to register
through the contract in the module docstring. While connected,
frontend submissions are automatically claimed and sent to the backend as
turns; no second human prompt is needed. The receiver maintains the lease and
submits the final receipt. Idle waiting does not start model turns. The page
displays the connection, backend, thread id, claimant, activity and any real
native approval request. It uses the CLI's existing login/model configuration,
without spawning sub-agents.

If this turn was started by the receiver, **do not call `/next` or `/result`**;
return the requested `status/message/result` JSON so the receiver can finish it.
For a manually connected interactive CLI, announce the claim explicitly, poll
with this session's own name (for example `agent=codex&wait=0`), then answer
through the result endpoint. Without a connected receiver or polling CLI, a
browser request stays queued; it does not wake the current development chat.
`recent_requests` in bridge status exposes the request id, state and named claimant.
The optional JSON `payload` is user context for your reasoning, not model settings
or executable CLI options. Limited proposals stay within the imported pool; generic
constructed search candidates cannot be used as extra limited copies.

## Protocol

```powershell
# 1. Long-poll for work (blocks up to 60s, then returns {"status":"wait"} — loop)
curl -s "http://127.0.0.1:8644/api/agent/next?agent=kimi"

# 2. If a request takes long, keep the claim alive (else it is re-queued after 60s)
curl -s -X POST http://127.0.0.1:8644/api/agent/heartbeat -d '{"request_id":"req-1","agent":"kimi"}'

# 3. Answer with evidence
curl -s -X POST http://127.0.0.1:8644/api/agent/result -d '{"request_id":"req-1","status":"ok","result":{...},"message":"..."}'

# State you can read
curl -s http://127.0.0.1:8644/api/snapshot     # deck + pool + stats + checks + avenues
curl -s "http://127.0.0.1:8644/api/find?q=f:pioneer%20t:creature&limit=20"
```

Result retrieval expires after 300s (410). Unknown `request_id` is 404;
answering a request you did not claim is 409. Exit the poll loop when the user
says the session is done or the hub is unreachable — never spin unattended.

Receiver controls: `POST /api/agent/connect`, `POST /api/agent/disconnect`,
`GET /api/agent/connection`. Native command/file approvals are presented on the
page and answered using `POST /api/agent/approval` with `approval_id` and
`decision` (`accept` or `decline`). No approvals are accepted automatically.
The receiver records its thread per backend in gitignored
`tools/cache/workbench_agent_session.json`; reconnecting resumes that thread
(a saved session from another backend starts fresh, never mixed). Failed resumes are explicit failures, not
silent new sessions. Disconnect interrupts active work and returns an error receipt.

## The four kinds

- **next_move** — Read `/api/snapshot` (stats, roles gaps, checks) and propose
  the single next action (e.g. "add 2x X, cut 1x Y" or "run audit --limited").
  Every card you name must come from `/api/find` or `python tools/mtg_tool.py
  search` results you actually fetched in this session. Cite the snapshot
  numbers that motivated the move.
- **explain** — Rules/stack/timing questions route to `skills/mtg-rules/`
  (`tools/mtg_rules_tool.py`); cite the CR rule numbers you actually queried,
  with effective date. Combo feasibility routes to `skills/mtg-combo/`.
- **novel_synergies** — Think of patterns, then land them: every proposed card
  must resolve through `/api/find` or `mtg_tool search` first. Write the result
  back with `POST /api/avenues` (`{"title","note","candidates":[{"name","reason"}]}`)
  so it shows on the page. Card names in avenues are marked
  `unverified_card_names` unless they came from find/search results — keep that
  mark true by only writing cards you verified this way.
- **handoff** — "Run the full pipeline" buttons. Follow `skills/mtg-deckbuilding/`
  stage 0b–5 against the current deck state (export via `/api/export` to a temp
  file, run the CLIs, report violations and fixes as structured `result`).

## Iron rule

Never name a card from memory. The deterministic kernel may name cards; you may
not — every card in every answer must trace to a `/api/find` or `mtg_tool`
search result fetched during the current request. A missing hit means "not
found", never "invent it".

## Failure semantics

Bridge down or page request malformed → say so, do not fabricate a result.
`status:"error"` results need a human-readable `message`. The page shows
`pending` while you work — if you cannot answer (e.g. network down for
find/search), return `status:"error"` with the reason instead of going silent;
the claim lease expires and the request re-queues, so silence wastes cycles.
