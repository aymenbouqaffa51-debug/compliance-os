# Compliance OS v3.2 — AI agent + modern frontend + Alembic

**Date:** 22 November 2026 · **112 tests passing** · 8 frontend routes build clean · agent verified live over HTTP

---

## What this release adds

### 1. The compliance agent

An assistant that answers questions about a client's compliance position by
RETRIEVING facts from the database and composing an answer from them.

**The design constraint that matters:** a compliance assistant that
hallucinates is worse than no assistant. If it says "your encryption control
passes" and the register says `gap`, the client repeats that to their auditor
and the engagement ends. So:

- Every answer is built from a retrieved `ContextBundle`.
- Every claim carries a citation (`control:A.8.8`, `monitor:PER-01`).
- When the facts do not support an answer, the agent says so and routes the user
to the right screen instead of guessing.
- The LLM layer, when configured, may only REWRITE the composed answer. It never
selects the facts. If it is unavailable the deterministic path produces the
full answer alone — so a self-hosted deployment in Morocco does not depend on a
US LLM provider being reachable, or on a CNDP transfer authorisation.

**Ten intents**, each with its own grounded answer builder:

| Intent | What it does |
|---|---|
| `gaps` | ranks open gaps by weight, flags missing owners and passed due dates |
| `readiness` | per-framework position, strongest/weakest, and an explicit "not audit-ready while N gaps" |
| `monitors` | last run score, each failing check with its observed value |
| `drift` | regressions since the previous run |
| `policies` | current versions and acknowledgement counts |
| `transfer` | CNDP position from the canonical list — **computed, never guessed** |
| `law0520` | whether the client is actually in scope, plus the art. 49 language trap |
| `dataprotection` | art. 12 prior authorisation, art. 23 processor contract, no statutory breach deadline |
| `priority` | a ranked fix order: weight first, then buyer-blocking items |
| `unknown` | declines, shows the real position as orientation, offers suggestions |

**Endpoints**

```
POST /api/clients/{id}/agent/ask        question -> grounded answer + citations
GET  /api/clients/{id}/agent/context    exactly what the agent can see
GET  /api/agent/suggestions             questions it can answer
```

`/agent/context` is a deliberate transparency feature: if the agent gives a bad
answer, the operator inspects the facts it reasoned from instead of guessing.

### 2. The frontend

Rebuilt as a real application shell rather than a set of pages.

**Design system** — one token block drives everything: a dark surface scale, a
semantic palette, and component classes (`.card`, `.btn-primary`, `.input`,
`.pill`, `.table`, `.track`) so contrast and spacing stay consistent. No icon
package: 18 inline SVGs keep the bundle small and the licence surface at zero.

**Application shell** — persistent sidebar with the client selector in the
header. Changing client broadcasts an event so every page follows. The agent
opens from the sidebar or the `Ask the agent` button.

**Pages** — 8 routes, all building clean:

| Route | Purpose |
|---|---|
| `/login` | split layout, TOTP prompt, proof panel |
| `/dashboard` | score rings per framework, metric tiles, remediation queue, dossier export |
| `/monitors` | check table with status pills, observed values, drift, outcome filters |
| `/questionnaires` | upload, inspect auto-drafts, edit inline, export MD/CSV |
| `/policies` | publish FR/EN, view body, record acknowledgements |
| `/integrations` | provider cards with explicit read-only permission notes |
| `/trust/[tenant]/[client]` | public, server-rendered trust centre |

**The agent panel** is a right-hand sheet with a transcript, citation chips,
follow-up buttons, and a "limited data" badge when the record does not support a
confident answer. It states its own constraint in the empty state: *answers come
only from your recorded data*.

### 3. Alembic migrations — the gap that mattered

The schema was created with `Base.metadata.create_all()`, which is fine for a
fresh install and useless for evolving one: it never alters or drops an existing
column, so a deployed instance silently diverges from the code.

Now in place:

- `backend/alembic.ini` + `backend/migrations/`
- The URL comes from `DATABASE_URL`, so no credential lands in version control
- `render_as_batch` on SQLite (which cannot ALTER most column properties in place)
- `compare_type` and `compare_server_default` on, so a changed column type is
caught by autogenerate
- Applied automatically at startup, falling back to `create_all()` only when
migrations are absent

**Verified:** `alembic revision --autogenerate` produced the initial migration;
`alembic upgrade head` created 14 tables from it.

---

## Three bugs found by testing, not by reading

**1. The agent answered "What is the capital of France?" as a hosting question.**
A bare country name matched the `transfer` intent, so an unrelated question got
a confident CNDP answer. Fixed by requiring a transfer context word
(host/transfer/residency/adequacy/F118/store) before a country name counts.
`13/13` classification cases now correct, with regression tests both ways —
including that real transfer questions still route.

**2. `_version_ge` parsed `"TLSv1.3"` as `[0, 3]`.** A protocol prefix was read
as a zero component. Now strips prefixes and compares numerically.

**3. The audit chain hashed different bytes on append and verify.**
`append_ledger` included `previous_hash` in its payload; `verify_ledger` popped
it before recomputing. The two could never agree. Both now hash the same bytes,
and a tampering test proves an edited record is caught.

---

## Test results

```
Engine   test_checks.py             18 passed
         test_engine.py             11 passed
         test_phase1_fixes.py       12 passed
         test_security.py           10 passed
         test_ssrf.py               12 passed
         test_vocabulary_lint.py     3 passed
                                   ──────────
                                    66 passed

API      test_agent.py              13 passed
         test_api.py                19 passed
         test_drift.py               2 passed
         test_workspace.py          12 passed
                                   ──────────
                                    46 passed

         TOTAL                     112 passed, 0 failed

Frontend next build                 8 routes, 0 type errors
Alembic  autogenerate + upgrade     14 tables created
Live     agent over HTTP            gaps, transfer, law0520, priority,
                                    nonsense-declined, context, suggestions
```

---

## Still open

| Gap | Effort | Consequence |
|---|---|---|
| Microsoft 365 collector | 2 days | Google Workspace and GitHub paths exist; M365 needs Graph credentials to test |
| Full ISO 93 controls + clauses 4–10 | 3 days | 61 operational Annex A controls ship |
| PDF/DOCX export | 2 days | Markdown + CSV only |
| Celery against real Redis | 0.5 day | compiles and is wired; not exercised end-to-end |
| Stripe billing | 2 days | manual invoicing |

Alembic was the gap that mattered before a paying client, and it is closed.
