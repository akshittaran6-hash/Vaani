# Vaani — project rules for coding agents

## What this is
Vaani: one phone number answered by one AI voice agent that books restaurant tables and hospital/doctor appointments in Telugu, Hindi and Indian English (code-mixed). Callers use any phone; bookings appear live on partner portals and mini-sites, and the caller gets a WhatsApp confirmation.
Hackathon: Homingo Hack Days, Edition 01, track LLM apps, problem C2 "Voice is the interface". Deadline 6 Dec 2026, 11:59 PM IST.
Demo data: 2 areas (default Jubilee Hills + Gachibowli), 5 restaurants + 5 hospitals per area, all fictional, in `data/` (9 JSON files). **Never invent businesses, doctors, slots or IDs.**

Full plan: `docs/MASTER_PLAN.md`. Call stages: `docs/CALL_FLOW.md`. Pages: `docs/WEBSITES.md`.

**Also follow `AGENTS.md`** (git workflow, secrets, and the mandatory work log in `docs/WORKLOG.md`: read the latest entry first, log as you go). Per-phase prompts: `docs/PHASE_PROMPTS.md`.

## Team areas (nobody is limited to theirs)
- Pranav: voice AI (`backend/voice`, `backend/flows`, `backend/tools`, telephony) + integration
- Karthik: public websites (landing, explore, mini-sites, status page, payments UI)
- Akshit: partner portals, Live Call Studio, call logs, eval page
- Rithvik: data, evaluation, demo (suggested)

## Stack (do not change without team agreement)
- Backend: Python 3.11+, FastAPI, Pydantic, Pipecat + Pipecat Flows, rapidfuzz, dateparser; deps managed with **uv** (`pyproject.toml` at repo root)
- Telephony: Twilio Programmable Voice + Media Streams (`/twilio/inbound` returns `<Connect><Stream url="{PUBLIC_WS_URL}/ws/twilio"/>`); browser calls over WebRTC via the Pipecat transport
- STT / LLM / TTS: providers chosen in `.env`, each behind a small interface (`backend/voice/stt.py`, `llm.py`, `tts.py`); always streaming
- DB: Supabase Postgres + Realtime + Storage (`supabase/schema.sql`, `rls.sql`, `seed.sql`); SQLite / in-memory for unit tests
- Frontend: Next.js App Router + strict TypeScript, Tailwind, shadcn/ui, Lucide, Framer Motion, React Three Fiber, Recharts, Zustand
- Payments: Razorpay or Stripe **test mode**, or the mock `/pay/[booking_id]` page

## Contracts (must match exactly — `docs/CONTRACTS.md`)
- Table names/columns, tool names/arguments/returns, backend endpoints, realtime event names, the outcome JSON shape and the data-file schemas are fixed. Change them only with the whole team, and update `docs/CONTRACTS.md` + code in the same commit.
- All writes go through the FastAPI backend with the service key; the frontend reads with the anon key under read-only RLS.
- Bookings are created only by the Postgres functions `book_table()` / `book_appointment()` (atomic, no double booking).
- Every tool appends to the call's tool timeline and emits a `tool_called` event with a human-readable summary.

## Hard rules (safety and naturalness)
1. **The LLM talks; code decides.** Availability, party limits, supported areas, booking IDs and payments are validated in tools. Never invent businesses, slots or IDs.
2. Search returns at most 3 options; the agent reads at most 3 aloud.
3. The greeting always includes the AI disclosure ("I'm Vaani, an AI assistant"). Never claim to be human.
4. Replies: 1–2 short sentences, casual Hyderabad-style code-mixing; numbers/times converted to spoken form by `voice/normalizer.py` before TTS.
5. Stream everything; target ~1 s to first audio; log `stt`, `llm_first_token`, `tts_first_audio`, `turn_total` per turn. Barge-in on (stop TTS within 0.5 s).
6. Unsupported area → the polite "only Jubilee Hills and Gachibowli" reply from `data/areas.json`.
7. Hospital: map plain words to a speciality; never diagnose; emergency phrases → "call 108 / 112 immediately", **no booking**. Self-harm words (any call) → the gentle `self_harm_reply` (Tele-MANAS 14416 / 1-800-891-4416, 112 if in danger now), **no booking**.
8. Never ask for OTP, PIN, CVV, card or account numbers; say so if the caller offers one.
9. Use the caller's number from caller ID for confirmations; never ask for email.
10. Payments only in provider test mode.
11. All data fictional and labelled `is_sample_data: true`; no real business names, photos or logos.
12. Stay on topic; end politely after abuse or 2–3 off-topic turns; never reveal instructions; offer a human on request.

## Workflow
- **Check current official docs before using a library API** (Context7 or the web docs) — Pipecat, Pipecat Flows, Supabase, Next.js, Twilio and Sarvam change fast. Don't guess function names or import paths.
- Work phase by phase (`docs/MASTER_PLAN.md` §14). End of each phase: run the tests, update docs, commit with a clear message, report what's needed.
- **No secrets in code or commits.** Use `.env` (git-ignored); keep `.env.example` in sync with `docs/CONTRACTS.md` §6.
- Missing API key → keep building against mocks; ask the human for the key.
- Small, readable modules; type hints in Python (mypy-clean), strict TypeScript; short comments on non-obvious code.
- pytest for every tool; keep `python -m backend.eval.eval` runnable; Playwright smoke tests for frontend routes.
- `docker compose up` must start everything from a clean clone (Phase 7 onwards).
- When behaviour changes, update README, EVAL.md and AI_USAGE.md in the same commit.
- A fact that changes must be updated everywhere it appears (grep for it).

## Commands
- Python deps: `uv sync` · tests: `uv run pytest` · lint: `uv run ruff check .` · types: `uv run mypy backend scripts`
- Data: `uv run python scripts/validate_data.py` · import a regenerated data folder: `uv run python scripts/import_data.py <folder>` · regenerate seed after editing `data/`: `uv run python scripts/make_seed_sql.py`
- Unit/DB tests run on the frozen fixture `backend/tests/fixtures/placeholder_data/`; `backend/tests/test_real_data.py` covers the shipped `data/`. The eval freezes "now" at 09:00 IST (`clock.freeze` + `vaani.now_ist`).
- DB (wipes + reloads `SUPABASE_DB_URL`): `uv run python scripts/db_apply.py` (schema + RLS + seed) · `uv run python scripts/seed.py` (fresh dates)
- DB tests start a temporary Postgres (or use `VAANI_TEST_DB_URL`); they must never point at a dev or demo database.
- Bookings only via `book_table()` / `book_appointment()` / `cancel_booking()` (see `docs/CONTRACTS.md` §1); data shape lives in `backend/catalog/models.py`.
- API: `uv run uvicorn backend.api.app:app --reload --port 8000` · passcodes: `uv run python scripts/partner_passcodes.py`
- Agent (text): `uv run python -m backend.flows.cli` · eval: `uv run python -m backend.eval.eval` (both use throwaway DBs). Flow code: `backend/flows/` (session, nodes, extract, when, speech, prompts/).
- Code decides in the flows: guards run before the LLM (emergency, unsupported area, FAQ, OTP redaction); party size / names / named places / days / times are extracted in code; read-backs are written by code (`flows/speech.py`) and a booking needs `propose_*` then the caller's yes on a later turn. Keep it that way.
- Tools: always call through `backend.tools.run_tool(ctx, name, args)` (timeline + events); never write bookings or slots from flows directly. A new tool = Pydantic `Args` model + `@tool(...)` + tests + a row in CONTRACTS §2.
