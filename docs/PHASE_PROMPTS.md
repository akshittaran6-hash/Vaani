# Vaani — phase prompts

One ready-to-paste prompt per phase, for whoever picks it up (Rithvik, Pranav or anyone) and whatever coding agent they use. Each prompt is self-contained and points the agent at the right files.

**How to use**

1. `git checkout main && git pull`, then `git checkout -b <branch from the table>`.
2. Copy the prompt for your phase into your agent (Claude Code, Codex, Cursor, …) and let it plan first.
3. The agent must follow `AGENTS.md`, especially the **work log** (`docs/WORKLOG.md`): an entry at the start, updated as it goes, finished at the end.
4. When done: checks green → PR into `main` → tick the phase in `docs/TEAM.md` and the table at the top of `docs/WORKLOG.md`.

| Phase | Status | Branch | Needs |
|---|---|---|---|
| 0 Repo + docs | ✅ done | — | — |
| 1 Data + database | ✅ done (local Supabase check open) | `chore/supabase-local-check` | Docker Desktop |
| 2 Tools + API | ✅ done | — | — |
| 3 Text-mode agent + eval | ✅ done (40/40 on placeholder data) | `phase-3-text-agent` | `LLM_*` in `.env` |
| 4 Voice over browser | ⬜ | `phase-4-voice` | Phase 3; `SARVAM_API_KEY` (+ optional TTS key) |
| 5 Websites | 🟡 Akshit + Karthik | `phase-5-frontend` | `docs/FRONTEND_PROMPT.md` |
| 6 Phone calls + WhatsApp | ⬜ | `phase-6-telephony` | Phase 4; Twilio trial + verified numbers; ngrok |
| 7 Integration, eval, deploy | ⬜ | `phase-7-integration` | Phases 3–6; Supabase project; Fly/Render/Railway + Vercel |
| 8 Submission polish | ⬜ | `phase-8-polish` | everything |

Every prompt below assumes the agent starts in the repo root (`vaani/`).

---

## Phases 0–2 (done, for reference)

Their output is on `main`; details in `docs/WORKLOG.md`. If you need to re-verify:

```text
Read AGENTS.md and docs/WORKLOG.md. Don't change code. Run: uv sync; uv run python scripts/validate_data.py;
uv run python scripts/make_seed_sql.py --check; uv run pytest -q; uv run ruff check .; uv run mypy backend scripts.
Report the results and add a short "verification" entry to docs/WORKLOG.md (timestamp from `date`).
```

### Open item from Phase 1: verify on local Supabase (needs Docker Desktop running)

```text
Read AGENTS.md, docs/WORKLOG.md, CLAUDE.md and docs/CONTRACTS.md §1 ("Row-level security"). Start a work-log entry.
Goal: prove the schema, RLS and Realtime work on a real Supabase stack (so far they were only tested on plain Postgres).
Steps: (1) check the Supabase CLI docs (Context7) for the installed version; `supabase start` from the repo root
(config is in supabase/config.toml). (2) Copy the API URL, anon key, service key and DB URL from `supabase status`
into .env (never commit it). (3) `uv run python scripts/db_apply.py` twice (must be idempotent). (4) Verify with SQL:
the 6 tables are in pg_publication_tables for supabase_realtime; as role anon, `select phone from bookings` fails while
`select booking_id, status from bookings` works; anon cannot insert anywhere or execute book_table. (5) Write a small
script or pytest (marker `supabase`, skipped without the env var) that subscribes to Realtime with the anon key
(supabase-py or supabase-js; check current docs), simulates a booking through the API and asserts the event arrives in
under 2 s and contains no phone column. Update EVAL.md's verification matrix and docs/TEAM.md; finish the work log; commit.
```

---

## Phase 3 — Text-mode agent + eval

**Branch:** `phase-3-text-agent` · **Needs:** `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` in `.env` (Featherless is set up; see WORKLOG).

```text
You are continuing Phase 3 of Vaani, a phone AI agent that books restaurant tables and doctor appointments in Telugu,
Hindi and Indian English. Read AGENTS.md first, then docs/WORKLOG.md (the Phase 3 handoff entry is the most important
thing to read), CLAUDE.md, docs/CALL_FLOW.md, docs/CONTRACTS.md §2 (tools) and §5 (outcome JSON), and
backend/tools/*.py. Start a work-log entry now and keep it updated.

GOAL
A text-only version of the full agent (no audio): Router → Restaurant agent | Hospital agent, driven by an LLM, using
the existing tools, chat-able from a CLI in te/hi/en, plus backend/eval/eval.py that replays the 40 scripted calls in
data/test_calls.json and reports accuracy split by te-en / hi-en / en-IN.

ALREADY BUILT (don't redo)
- backend/tools/: 14 tools behind backend.tools.run_tool(ctx, name, args): timeline + tool_called events, coded errors.
- backend/voice/llm.py: JSON action protocol. The model returns {"say": "...", "actions": [{"tool", "args"}]};
  OpenAICompatLLM, ScriptedLLM (for tests), parse_reply, from_env(). Native tool calling is broken on Featherless (see
  WORKLOG); keep the JSON protocol as the default.
- backend/flows/language.py (detect_language), backend/flows/when.py (parse_day, parse_time). Known bug: parse_time
  returns None for "8:30", "10:15", "7:30 pm", "saayantram 4:30", "12 noon". Fix it first: match times on the raw
  lower-cased text, not norm()'s output. Then unit-test all of these: "8:30 chalega" (restaurant) → 20:30,
  "saadhe aath baje" → 20:30, "enimidinnara ki" → 20:30, "okati gantaki" → 13:00, "7:30 pm" → 19:30,
  "raat 9 baje" → 21:00, "11 ki" (hospital) → 11:00, "saayantram 4:30" (hospital) → 16:30, "12 noon" → 12:00,
  "10:15" (hospital) → 10:15, "shaam 6 baje" → 18:00, "sava saat" → 19:15; parse_day: kal/repu → +1,
  parso/ellundi → +2, "3 din baad" → +3, "naalugu rojula tarvata" → +4, weekdays, ISO.
- backend/devdb.py: ephemeral Postgres + seeded template DB + clone() (one fresh DB per eval call).

BUILD
1. backend/flows/context.py: CallContext dataclass (call_id, phone, channel, language, service, node, slots {area_id,
   business_id, doctor_id, speciality, date, time, party_size, name}, pending booking, booking_id, outcome, intent,
   flags for eval: search_result_ids, offered_alternatives, faq_answered, unsupported_heard, emergency, turn counter,
   transcript list with language tags) + to_outcome_json() exactly in the CONTRACTS §5 shape.
2. backend/flows/nodes.py: node specs that mirror Pipecat Flows' NodeConfig (check the current pipecat-flows docs on
   Context7: role_message, task_messages, functions as FlowsFunctionSchema-like {name, description, properties,
   required, handler}), with handlers async (args, session) -> (result_dict, next_node_name | None), so Phase 4 can
   wrap them in a FlowManager without rewriting.
   - router: greet with the AI disclosure, detect language, route_to(service), one clarifying question if unclear.
   - restaurant: search_restaurants (accepts area words, date/time words and resolves them in code with resolve_area,
     parse_day, parse_time), get_slots, answer_faq, propose_booking (validates and stores a pending read-back),
     confirm_booking (books only if a pending read-back exists from an EARLIER turn; then send_confirmation and,
     if a deposit is due, create_payment_link).
   - hospital: map_need (map_speciality), search_hospitals, get_doctor_slots, answer_faq, propose_appointment,
     confirm_booking.
   - global in every node: set_language, switch_service, transfer_to_human, end_call.
   Business and doctor arguments may be ids or names: resolve them in code (exact id, then fuzzy name).
3. backend/flows/session.py: Session(services, llm, phone, channel) with start() → greeting (agent_phrases
   greeting_with_ai_disclosure; default Telugu) and handle(text) → reply. Per turn: transcript + `transcript` event;
   first turn: detect_language + language_detected event. Deterministic guards before any LLM call: an emergency phrase
   while service is router/hospital → speak speciality_mapping emergency_reply in the caller's language, outcome
   redirected_emergency, no booking possible afterwards, no LLM call; OTP/PIN/CVV/card/account-number mention → the
   never_ask_otp line. Then an LLM loop (max 4 steps): rebuild the system prompt each step (rules + language style +
   current node task + the node's functions with argument schemas + a calendar of today..+6 with en/hi/te day words +
   known details + 3 example dialogues for this service and language), send history (assistant turns = the raw JSON,
   tool results = a user message wrapped in <tool_results>…</tool_results>), execute actions through the node
   functions, follow node transitions, stop at a reply with no actions. Collect filler "say" lines for Phase 4.
   Emit agent_switched / slot_filled / booking_created / call_ended events. end() writes the calls row (transcript,
   outcome_json, tool_timeline, latency_json with LLM ms per step, 2-line summary).
4. Prompts in backend/flows/prompts/: rules.md (shared, English; the hard rules from CLAUDE.md), and per language
   {te,hi,en}/style.md + examples_restaurant.md + examples_hospital.md with 3–5 short, natural Hyderabad-style example
   dialogues each (use the names from data/ and the sample calls in docs/CALL_FLOW.md). 1–2 sentences per reply, never
   more than 3 options, numbers and times written as the caller would say them.
5. backend/flows/cli.py: `uv run python -m backend.flows.cli [--lang te|hi|en] [--db-url URL]`. Without --db-url it
   starts an ephemeral DB (backend/devdb.py); never use SUPABASE_DB_URL by default (seeding wipes it). Prints Vaani's
   replies and, dimmed, each tool summary.
6. backend/eval/eval.py: `uv run python -m backend.eval.eval [--only T01,T21] [--concurrency 8]`. One fresh cloned DB
   per test call, scripted caller turns from test_calls.json, then score:
   booking accuracy (business, doctor, day_offset, time, party size all match the real booking row), expected business
   in top 3 (only when a search ran), unsupported area handled, emergency → 108/112 with no booking, slot full → 2
   nearest offered, FAQ answered, outcome match. Split every metric by language_mix. Print a markdown table plus one
   line per failed call with the reason, save JSON to backend/eval/results/ (git-ignored) including LLM latency
   (median and p95) and token usage → estimated $ cost.
7. Tests (ScriptedLLM, no network): parsers; a full restaurant booking flow; a hospital booking flow;
   confirm_booking without a prior read-back is refused; the emergency guard never calls the LLM; the OTP guard; an
   unknown action and invalid JSON are handled; outcome JSON shape; eval scoring on fake results. Keep everything
   currently passing.

RULES: the LLM talks, code decides; the LLM never sees the phone number; never more than 3 options; no booking after an
emergency; the greeting always says Vaani is an AI. Don't change docs/CONTRACTS.md shapes without recording it there.

DONE WHEN: you can book a table in Hindi and an appointment in Telugu from the CLI; eval runs on all 40 calls against
the real LLM; results are in EVAL.md (by language, with date, model and cost); pytest, ruff and mypy are green; the work
log has a final entry with the numbers and the next steps for Phase 4. Commit on phase-3-text-agent and open a PR.
```

---

## Phase 4 — Voice over browser

**Branch:** `phase-4-voice` · **Needs:** Phase 3 merged; `SARVAM_API_KEY` (STT + Bulbul TTS); optional backup TTS key.

```text
Read AGENTS.md, docs/WORKLOG.md (latest entries), CLAUDE.md, docs/MASTER_PLAN.md §9, docs/CALL_FLOW.md,
docs/ARCHITECTURE.md and the Phase 3 code in backend/flows/. Start a work-log entry.

GOAL: talk to Vaani in the browser by voice, with the same flows and tools as Phase 3, ~1 s to first audio, barge-in
under 0.5 s.

WHAT PHASE 3 LEFT YOU (read backend/flows/session.py first): the whole conversation brain is Session.handle(text) →
TurnResult(reply, fillers, actions, guard). It already does redaction, language detection, extraction, the deterministic
guards (emergency, unsupported area, FAQ, OTP), code-written read-backs and confirmation, and the JSON-action LLM loop.
The LLM is Featherless Qwen3-30B-A3B-Instruct-2507 via the JSON protocol in backend/voice/llm.py (native tool calling
failed there): ~1.5 s median per LLM step, often 1–2 steps per turn, and many turns need no LLM at all (guards,
auto read-back, plain-yes confirm). Recommended first approach: a custom Pipecat FrameProcessor that takes final
transcriptions, calls Session.handle, speaks the first filler at once while it runs, then the reply. Measure it before
deciding whether to move to Pipecat Flows' FlowManager with a native-tool-calling provider (nodes.py is already in
NodeConfig / FlowsFunctionSchema shape for that). Either way keep every guard and the read-back rule. Don't
reimplement them in prompts.

CHECK CURRENT DOCS FIRST (Context7 / official): Pipecat (pipeline, SmallWebRTCTransport or the current WebRTC
transport, VAD/Silero, smart turn detection, interruptions, observers/metrics), Pipecat Flows (FlowManager,
NodeConfig, FlowsFunctionSchema), Pipecat's Sarvam STT/TTS services (or write thin adapters on Sarvam's streaming
APIs), and the Pipecat client JS SDK for the test page. Don't guess import paths.

BUILD
1. backend/voice/stt.py, tts.py (and reuse llm.py): small provider interfaces chosen by STT_PROVIDER / TTS_PROVIDER,
   Sarvam by default, with mocks. en-IN voices only for English. Decide native tool calling vs the JSON protocol for
   the live pipeline (Pipecat expects native function calls; if the provider can't do them reliably, use a
   provider/model that can, e.g. Groq or OpenAI, and record the decision and its latency/cost in EVAL.md).
2. backend/flows/pipecat_adapter.py: turn the Phase 3 node specs into Pipecat Flows NodeConfig / FlowsFunctionSchema;
   keep the CallContext in flow_manager.state; same guards (emergency, OTP) as Phase 3.
3. backend/voice/pipeline.py: one pipeline per call: transport in → VAD + turn detection → STT → (guards) → LLM via
   Flows → normalizer → TTS → transport out. Barge-in on. Fillers from agent_phrases while tools run. Silence handler:
   silence_check line twice, then goodbye. Latency observer logging stt, llm_first_token, tts_first_audio and
   turn_total per turn → `latency` events + calls.latency_json.
4. backend/voice/normalizer.py: times, dates, ₹ amounts and party sizes → natural spoken te / hi / en-IN before TTS
   ("20:30" → "saadhe aath baje" / "raatri enimidinnara" / "eight thirty PM"; "₹500" → "paanch sau rupaye" /
   "aidu vandala rupayalu"; "VN-4821" read digit by digit). Thorough unit tests.
5. POST /webrtc/offer in the FastAPI app (one pipeline per peer connection); a minimal test page served by the backend
   (e.g. /voice-test) using the Pipecat JS client to talk from the browser.
6. backend/postcall/: finalise transcript with language tags, outcome JSON, tool timeline, latency, 2-line summary →
   calls row; call_ended event. Reuse what Session.end() already does.
7. Tests: normalizer; adapter (node → NodeConfig); the pipeline with mocked STT/TTS/LLM services (text frames in,
   expected tool calls + TTS text out); latency fields present.

DONE WHEN: a full restaurant booking and a hospital booking work by voice in Chrome; the latency table (median and
slowest per stage) and barge-in time are measured and written to EVAL.md; tests green; work log finished; PR opened.
```

---

## Phase 5 — Websites (Akshit + Karthik)

**Branch:** `phase-5-frontend` (or their own feature branches) · **Prompt:** `docs/FRONTEND_PROMPT.md`.

The frontend team builds from `docs/FRONTEND_PROMPT.md`. Where it differs from the backend, follow the
"Frontend ↔ backend notes" table in `docs/WEBSITES.md` (passcodes via `X-Partner-Passcode`, masked phones,
`"vaani"` transcript speaker, mock-pay endpoint, response shapes).

Integration prompt, for whoever merges their app into this repo:

```text
Read AGENTS.md, docs/WORKLOG.md, docs/WEBSITES.md (especially "Frontend ↔ backend notes"), docs/CONTRACTS.md §3–4 and
frontend/README.md. Start a work-log entry.
GOAL: the Next.js app in frontend/ runs in live mode against this backend and Supabase.
Steps: (1) run the backend (uv run uvicorn backend.api.app:app --port 8000) on a seeded DB and the frontend with
NEXT_PUBLIC_DATA_MODE=live. (2) Fix every mismatch in the frontend's single mapping layer, not in the backend contract
(if the contract really must change, update docs/CONTRACTS.md and the backend tests in the same PR). (3) Partner login:
verify a passcode by calling GET /api/partners/{id}/bookings with X-Partner-Passcode. (4) Run the acceptance test with
POST /api/dev/simulate-booking: the portal flash, mini-site chip and status page update in under 2 s; a slot blocked on
the portal is refused by the next booking. (5) Playwright smoke tests pass for every route. Record timings in EVAL.md,
finish the work log, open a PR.
```

---

## Phase 6 — Live phone calls + WhatsApp confirmations

**Branch:** `phase-6-telephony` · **Needs:** Phase 4; Twilio trial account (SID, auth token, number, WhatsApp sandbox sender), all team phones verified and joined to the sandbox; ngrok for a public `wss://` URL. Ask Pranav for the credentials; they go in `.env` only.

```text
Read AGENTS.md, docs/WORKLOG.md, CLAUDE.md, docs/MASTER_PLAN.md §9, docs/CONTRACTS.md §3 and docs/LIMITS.md
(Twilio trial limits). Start a work-log entry.
CHECK CURRENT DOCS FIRST: Twilio Programmable Voice TwiML <Connect><Stream>, Media Streams, the Twilio WhatsApp
sandbox, Twilio request signature validation, and Pipecat's Twilio serializer / websocket transport.
BUILD
1. POST /twilio/inbound: validate the Twilio signature; return TwiML <Connect><Stream url="{PUBLIC_WS_URL}/ws/twilio"/>,
   passing the caller's number (and the call SID) as stream parameters.
2. WS /ws/twilio: the same Phase 4 pipeline with Pipecat's Twilio serializer (8 kHz μ-law); the caller ID becomes the
   CallContext phone (never ask for it); channel "phone"; masked number in events.
3. DTMF language fallback: after one unclear first turn, say "Telugu ki 1, Hindi ki 2, English ki 3"; handle
   1/2/3 key presses → set the language and the voice.
4. backend/messaging.py: TwilioMessenger (WhatsApp first, SMS fallback) behind the existing Messenger interface,
   chosen when the Twilio env vars are set; keep MockMessenger for tests. Also a "payment received" WhatsApp message
   when a booking becomes paid.
5. Payment links: if PAYMENT_PROVIDER=razorpay (or stripe), create real test-mode links and parse their webhooks
   (check the provider's current docs; Razorpay uses HMAC-SHA256 in X-Razorpay-Signature). Keep mock as the default.
6. Tests: TwiML response, signature check, DTMF handling, messenger fallback (mocked HTTP), webhook parsing.
DONE WHEN: a real phone call books a table and the WhatsApp card arrives; 4 simultaneous calls from verified phones all
succeed (record per-call latency and outcome in EVAL.md); trial minutes used are noted; work log finished; PR opened.
```

---

## Phase 7 — Integration, eval, deploy

**Branch:** `phase-7-integration` · **Needs:** Phases 3–6; a hosted Supabase project; a Fly.io / Render / Railway account (region near India); Vercel for the frontend.

```text
Read AGENTS.md, docs/WORKLOG.md, docs/MASTER_PLAN.md §14, EVAL.md, docs/DEMO.md and docs/ARCHITECTURE.md (Hosting).
Start a work-log entry.
BUILD
1. End-to-end tests (scripted, using the dev simulate endpoint and, where possible, a real browser/phone run):
   Hindi restaurant call → portal flash + mini-site slot drop + WhatsApp in under 2 s; Telugu hospital call → fee link →
   test payment → "Paid" on the status page and portal; a blocked slot is refused on the next call.
2. backend/eval/load_test.py: N simulated callers (1 / 4 / 10 / 15) streaming recorded audio from
   backend/eval/recordings/ through the WebRTC (or websocket) path; record median and slowest time to first audio and
   success %. Fill EVAL.md and the data the /eval page reads.
3. Final eval.py run on the real data set (if the ChatGPT data from docs/DATA_PROMPT.md has landed: validate, seed,
   re-run). Fill every EVAL.md row, including cost per call minute (telephony + STT + LLM + TTS).
4. Dockerfiles for backend/ and frontend/; docker-compose.yml so `docker compose up` works from a clean clone (Supabase
   via its CLI or the hosted project).
5. Deploy: voice server on Fly.io/Render/Railway near India (websockets!), frontend on Vercel, Supabase hosted project
   (db_apply.py with the hosted DB URL), Twilio webhook pointed at the deployed URL. Write a "Deploy" section in
   README.md. Set DEV_SIMULATE=false and a real PARTNER_PASSCODE_SECRET in production.
DONE WHEN: all E2E checks pass on the deployed stack, EVAL.md has real numbers, a clean clone runs with docker compose
up, the work log is finished, and a PR is open.
```

---

## Phase 8 — Submission polish

**Branch:** `phase-8-polish` · **Deadline:** 6 Dec 2026, 11:59 PM IST (captain submits a day early).

```text
Read AGENTS.md, docs/WORKLOG.md, README.md (submission checklist), docs/DEMO.md, docs/LIMITS.md, ATTRIBUTIONS.md and
AI_USAGE.md. Start a work-log entry.
DO
1. README: real screenshots of every page (light/dark, mobile, TV mode), a demo GIF, a clean architecture diagram,
   setup in one command, known limits, the live URL and callable number, and a link to the demo video.
2. ATTRIBUTIONS.md: every library, API, voice, font, image and data source with its licence. AI_USAGE.md: final
   account of how AI tools were used, who reviewed the code, and that callers are told they're talking to an AI.
3. EVAL.md: final verification matrix with real numbers and dates.
4. Demo checklist from docs/DEMO.md rehearsed; backup video recorded.
5. Pitch deck outline: problem → traditional vs voice-first → live demo → how it works → evidence → safety → company
   potential.
6. Tick every item of the README submission checklist; make sure the repo is public and contains no secrets
   (git log -p | grep for key patterns).
DONE WHEN: the checklist is complete, the work log is finished, and the final PR is merged.
```
