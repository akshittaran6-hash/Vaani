# Vaani — Architecture

Every call runs through one engine and lands in one database, which pushes changes live to every website.

```
 Phone (any phone)                                   Browser ("Talk to Vaani")
 Twilio number ─ Media Streams websocket             WebRTC via the Pipecat client SDK
                    \                                   /
                     ▼                                 ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │ Voice server · FastAPI + Pipecat  (one pipeline per live call)          │
 │ VAD + turn detection → streaming STT → LLM → normaliser → streaming TTS │
 │ barge-in · fillers · silence handler · latency logged per turn          │
 ├────────────────────────────────────────────────────────────────────────┤
 │ Conversation flows · Pipecat Flows                                      │
 │   Router (greet, language, intent) → Restaurant agent | Hospital agent  │
 ├────────────────────────────────────────────────────────────────────────┤
 │ Tools · every rule enforced in code                                     │
 │   resolve_area · search_* · get_*_slots · book_* · map_speciality ·     │
 │   answer_faq · send_confirmation · create_payment_link                  │
 ├────────────────────────────────────────────────────────────────────────┤
 │ REST API · Twilio webhooks · payment webhook · dev simulate             │
 └──────────────────────────────┬─────────────────────────────────────────┘
                                │ service key (all writes)
                                ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │ Supabase · Postgres + Realtime + Storage                                │
 │ areas · restaurants · tables · slots · hospitals · doctors · bookings · │
 │ payments · calls · call_events   (atomic booking functions, RLS)        │
 └───────┬───────────────────────────┬─────────────────────────┬──────────┘
         │ anon key, read-only RLS   │                         │
         ▼   + Realtime              ▼                         ▼
 Next.js websites              WhatsApp / SMS (Twilio)     Payments (test mode)
 mini-sites · partner portals  confirmation card           Razorpay / Stripe / mock
 (TV) · studio · logs · eval   "payment received"          → webhook → booking "paid"
```

## Components

| Component | Path | Responsibility |
|---|---|---|
| Transports | `backend/voice/transports/` | Twilio Media Streams (`/ws/twilio`, Pipecat Twilio serializer, DTMF) and WebRTC (`/webrtc/offer`). Same pipeline for both |
| Pipeline | `backend/voice/pipeline.py` | Builds one Pipecat pipeline per call: VAD, turn detection, STT, LLM, normaliser, TTS, barge-in, silence handler, latency observer |
| Provider adapters | `backend/voice/stt.py`, `llm.py`, `tts.py` | Small interfaces chosen by env (`STT_PROVIDER`, `LLM_BASE_URL`/`LLM_MODEL`, `TTS_PROVIDER`) so we can compare stacks |
| Normaliser | `backend/voice/normalizer.py` | Times, dates, ₹ amounts, party sizes → natural spoken te / hi / en-IN before TTS |
| Flows | `backend/flows/` | `nodes.py`: router / restaurant / hospital nodes shaped like Pipecat Flows (`NodeSpec`, `FunctionSpec` with handlers → `(result, next_node)`). `session.py`: per-turn runner: redaction → language → extraction → guards (emergency, unsupported area, FAQ, OTP) → plain-yes confirm / auto read-back → LLM action loop. `extract.py` + `when.py`: party size, names, named places, days, times from te/hi/en words. `speech.py`: code-written read-backs and spoken times. `context.py`: `CallContext` + outcome JSON. `prompts/`: rules + per-language style and examples. `cli.py`: text chat |
| LLM adapter | `backend/voice/llm.py` | OpenAI-compatible client with a **JSON action protocol** (`{"say", "actions": [{"tool", "args"}]}`) instead of native tool calling, which was failing on Featherless; tolerant parser; `ScriptedLLM` for tests |
| Tools | `backend/tools/` | Implement `CONTRACTS.md` §2 behind one runner (`run_tool`): Pydantic-validated args, coded errors, tool timeline, `tool_called` events |
| Catalog | `backend/catalog/` | Pydantic models for the 9 data files, loader, cross-file validation, slot schedules (`schedule.py`), seed SQL generation |
| Data access | `backend/store.py` (async pool), `backend/db.py` (scripts) | The backend talks to Supabase Postgres directly over `SUPABASE_DB_URL`: lower latency per voice turn and real transactions; Realtime still fires because it watches the database. **Catalogue text** (names, aliases, ratings, rules, FAQs, phrases) is read from `data/` at startup; **live state** (slots, blocks, leave, bookings, payments, calls, events) always from Postgres |
| Messaging, payments | `backend/messaging.py`, `backend/payments.py` | Messenger interface (mock now, Twilio in Phase 6); test-mode payment links, HMAC webhook check, `mark_paid` |
| Post-call | `backend/postcall/` | Transcript with language tags, outcome JSON, tool timeline, latency, 2-line summary → `calls` |
| API | `backend/api/` | REST endpoints, Twilio webhooks, payment webhook (signature check), dev simulate |
| Eval | `backend/eval/` | `eval.py` + `scoring.py` (text replay of `test_calls.json`, one cloned throwaway DB per call via `backend/devdb.py`, table by language, JSON to `results/`), `load_test.py` (Phase 7) |
| Database | `supabase/` | `schema.sql`, `rls.sql`, `seed.sql` (generated, dates relative to `vaani_today()`), CLI `config.toml`; booking functions lock slot rows; Realtime publication |
| Data | `data/`, `scripts/` | 9 JSON files, `validate_data.py`, `seed.py`, `make_seed_sql.py`, `db_apply.py` |
| Frontend | `frontend/` | Next.js App Router: landing, explore, mini-sites, booking status, mock pay, partner portals (TV), studio, call logs, eval |

## Data flow for one booking

1. Caller speaks → STT → LLM picks `book_table` (only after confirmation).
2. Tool validates and calls Postgres `book_table()` → booking row + updated `restaurant_slots` row in one transaction.
3. Tool emits `booking_created` into `call_events`; Supabase Realtime pushes the `bookings`, `restaurant_slots` and `call_events` changes.
4. Partner portal flashes + chimes, mini-site slot count drops, Studio timeline updates (target < 2 s end to end).
5. `send_confirmation` sends the WhatsApp card with `<site>/b/VN-xxxx`.

## Hosting

| Piece | Where | Why |
|---|---|---|
| Voice server | Fly.io / Render / Railway, region near India (e.g. Mumbai/Singapore) | Long-lived websockets; Vercel can't hold them |
| Frontend | Vercel | Next.js native |
| Database | Supabase (hosted project for the demo; local CLI stack for dev) | |
| Local dev | ngrok for a public `wss://` URL that Twilio can reach | |

## Design principles

- **The LLM talks; code decides.** Nothing the LLM says can create a booking without a tool passing its checks.
- **Swappable providers.** Every external service is behind a small interface + env vars, with a mock for tests.
- **One source of truth.** Contracts in `CONTRACTS.md`; schema in `supabase/schema.sql`; data in `data/`.
