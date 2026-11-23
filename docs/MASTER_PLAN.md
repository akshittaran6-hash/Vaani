# Vaani — Master Plan

> One phone number, answered by one AI, that books restaurant tables and hospital appointments in Telugu, Hindi and Indian English over a real live call.

This is the organised version of the build brief (`docs/SOURCE_PROMPT.md`) and the team plan (`docs/master-plan.html`). Where a topic has its own doc, this file summarises and links to it so each fact lives in one place.

| § | Topic | Detail in |
|---|---|---|
| 1 | What Vaani is | here |
| 2 | How a call works | [CALL_FLOW.md](CALL_FLOW.md) |
| 3 | Architecture | [ARCHITECTURE.md](ARCHITECTURE.md) |
| 4 | Tech stack | here |
| 5 | Folder structure | here |
| 6 | Contracts | [CONTRACTS.md](CONTRACTS.md) |
| 7 | Data | [DATA_PROMPT.md](DATA_PROMPT.md), [CONTRACTS.md §7](CONTRACTS.md) |
| 8 | Websites | [WEBSITES.md](WEBSITES.md), frontend build prompt [FRONTEND_PROMPT.md](FRONTEND_PROMPT.md) |
| 9 | Voice AI details | here |
| 10 | Demo | [DEMO.md](DEMO.md) |
| 11 | Evaluation | [../EVAL.md](../EVAL.md) |
| 12 | Costs and known limits | [LIMITS.md](LIMITS.md) |
| 13 | Safety and naturalness | here + [../CLAUDE.md](../CLAUDE.md) |
| 14 | Phases | here; checklists in [TEAM.md](TEAM.md); per-phase prompts in [PHASE_PROMPTS.md](PHASE_PROMPTS.md); progress in [WORKLOG.md](WORKLOG.md) |

---

## 1. What Vaani is

Vaani is **one phone number answered by one AI voice agent** that books **restaurant tables** and **hospital/doctor appointments** for callers speaking **Telugu, Hindi and Indian English** (code-mixed speech is normal). Callers use any phone — no app, no internet. A booking made on a call appears live on the business's partner portal and public mini-site, and the caller gets a WhatsApp confirmation.

**Hackathon:** Homingo Hack Days, Edition 01 · Track: LLM apps · Problem statement **C2 "Voice is the interface"** — apps where voice is the whole product: they take the call, understand people however they speak, and get the thing done.

**Judges look for:** works live on a real problem · measured evidence (not just a demo) · ambition · company potential. The LLM apps track adds grounded answers, measured quality, attention to UX, latency and cost.

**Submission:** public GitHub repo with README + setup steps, a short demo video; optional deployed URL + pitch deck (we do both). **Deadline 6 Dec 2026, 11:59 PM IST** (captain submits a day early).

**Team PARK:** Pranav (voice AI + integration), Karthik (public websites + payments), Akshit (partner portals + studio + logs + eval page), Rithvik (data, evaluation, demo — suggested). Anyone can work on anything. See [TEAM.md](TEAM.md).

### Problems we solve

| Problem | Traditional way | Vaani way |
|---|---|---|
| Language barriers | Apps and IVRs mostly in English or formal Hindi | Speak Telugu, Hindi or Indian English, mixed freely |
| Limited digital literacy | Forms, apps, OTP flows | Just talk; the AI fills everything in |
| Complicated booking apps | Many screens, filters, sign-ups | One call, one minute |
| Can't or won't type | Elderly people, busy workers, non-Latin script users | Voice only |
| Accessibility limits | Low vision, low literacy, keypad phones | Works on any phone, no app, no internet |
| Poor customer service | "Press 1, press 2", hold times, limited hours | Answers instantly, 24/7, many calls at once |

**Pitch line:** Most Indians would rather talk than type, but every service is still built for typing. Vaani works on every phone in India, even without internet.

### Scope

- **Two services:** restaurant table booking; hospital/doctor appointment booking.
- **Two demo areas in Hyderabad:** Jubilee Hills and Gachibowli (defaults until confirmed; set by `DEMO_AREA_1/2`). 5 restaurants + 5 hospitals per area = **20 fictional businesses**.
- **Any other area** → *"For this demo we only cover Jubilee Hills and Gachibowli. Shall I check one of these?"*
- **Languages:** Telugu, Hindi, Indian English (en-IN voices only, never British/US accent). Tamil, Kannada, Malayalam are "supported, being tuned" — designed for, but we test the first three.
- **Out of scope** (pitched as future playbooks on the same engine): government schemes, bank status, bus tickets, surveys, payment reminders.
- **Scale story:** search returns only the top 3, so the design works for 20 or 300 businesses.

## 4. Tech stack

| Layer | Choice | Backup |
|---|---|---|
| Frontend | Next.js (App Router) + TypeScript, Tailwind CSS, shadcn/ui, Lucide, Framer Motion, React Three Fiber (audio-reactive voice orb), Recharts, Zustand | — |
| Realtime | Supabase Realtime | backend websocket |
| Browser call client | Pipecat client SDK (WebRTC) | Daily / LiveKit |
| Backend | Python 3.11+, FastAPI, Pydantic, rapidfuzz, dateparser + custom Telugu/Hindi time parser | — |
| Voice pipeline | Pipecat + Pipecat Flows | LiveKit Agents |
| Telephony | Twilio Programmable Voice + Media Streams (trial) | Exotel / Plivo later (Indian numbers need business KYC) |
| Confirmations | Twilio WhatsApp sandbox | SMS |
| STT | Sarvam | Deepgram / Whisper |
| LLM | OpenAI-compatible API set by env (`LLM_BASE_URL`, `LLM_MODEL`); fastest model that returns reliable JSON | Groq / OpenAI / Gemini / Featherless |
| TTS | Sarvam Bulbul (configurable) — final pick by blind voice test | ElevenLabs / Azure / Google |
| DB | Supabase Postgres + Realtime + Storage | SQLite / in-memory for unit tests |
| Payments | Razorpay or Stripe test-mode links + webhook | mock `/pay/[booking_id]` page |
| Packaging | Docker + `docker compose up`, pytest, Playwright (frontend smoke tests), uv (Python deps) | — |

Every provider is swappable behind a small interface (`stt.py`, `llm.py`, `tts.py`) driven by env vars, because we will compare stacks.

## 5. Folder structure

```
vaani/
├── docs/            MASTER_PLAN, ARCHITECTURE, CONTRACTS, CALL_FLOW, WEBSITES, DEMO, DATA_PROMPT, FRONTEND_PROMPT, TEAM, LIMITS, master-plan.html, SOURCE_PROMPT
├── frontend/        Next.js app
├── backend/
│   ├── voice/       pipeline, transports (twilio, webrtc), stt/llm/tts adapters, normalizer
│   ├── flows/       router, restaurant, hospital (Pipecat Flows) + prompts/{te,hi,en}
│   ├── tools/       tool implementations
│   ├── postcall/    transcript, outcome, tool timeline, latency, summary
│   ├── api/         REST routes, Twilio webhooks, payment webhook, dev simulate
│   ├── eval/        eval.py, load_test.py, recordings/
│   └── tests/
├── data/            9 JSON files
├── scripts/         validate_data.py, seed.py, make_seed_sql.py, db_apply.py
├── supabase/        schema.sql, rls.sql, seed.sql (+ CLI config)
├── docker-compose.yml
├── CLAUDE.md  README.md  LICENSE  ATTRIBUTIONS.md  AI_USAGE.md  EVAL.md
└── .env.example  .gitignore  pyproject.toml
```

## 9. Voice AI details

- **One Pipecat pipeline per call**; the same pipeline and flows serve WebRTC and Twilio.
- **Twilio:** `POST /twilio/inbound` returns TwiML `<Connect><Stream url="{PUBLIC_WS_URL}/ws/twilio"/></Connect>`; `WS /ws/twilio` uses Pipecat's Twilio serializer. The caller's number from Twilio is the booking phone (never ask for email). DTMF supports the language fallback.
- **Streaming everywhere:** STT, LLM and TTS stream; start speaking the first sentence early. Target **~1 s to first audio**. Log `stt`, `llm_first_token`, `tts_first_audio`, `turn_total` per turn.
- **Barge-in:** stop TTS within 0.5 s when the caller speaks.
- **`voice/normalizer.py`:** times, dates, ₹ amounts and party sizes → natural spoken te / hi / en-IN before TTS (e.g. `20:30` → "saadhe aath baje" (hi) / "raatri enimidinnara" (te) / "eight thirty pm" (en)). Unit-tested.
- **Fillers** during tool calls; backchannels; 3 variations per phrase from `agent_phrases.json`.
- **Router node:** greeting with disclosure, language detection, `route_to(service)`; global functions `switch_service`, `transfer_to_human`, emergency redirect, `end_call`; shared `CallContext` (phone, name, language, current_service).
- **Restaurant and hospital nodes** follow [CALL_FLOW.md](CALL_FLOW.md); each node sees only its own tools.
- **Prompts** live in `backend/flows/prompts/{te,hi,en}/…` with 3–5 example dialogues per service.
- **Post-call processor** writes the `calls` row: transcript with language tags, outcome JSON, tool timeline, latency, 2-line summary.

## 13. Safety and naturalness rules

1. **The LLM talks; code decides.** Availability, party limits, supported areas, booking IDs and payments are validated in tools. Never invent businesses, slots or IDs.
2. Search returns at most 3; the agent reads at most 3.
3. The greeting always includes "I'm Vaani, an AI assistant". Never claim to be human.
4. 1–2 short sentences per reply, casual Hyderabad-style code-mixing, numbers/times in spoken form.
5. Stream everything; ~1 s to first audio; barge-in on.
6. Unsupported area → polite reply from `areas.json`.
7. Hospital: map plain words to a speciality; never diagnose; emergency phrases → "call 108 / 112 immediately", no booking. Self-harm words (any call) → a gentle reply with Tele-MANAS 14416 and 112, no booking.
8. Never ask for OTP, PIN, CVV, card or account numbers; say so if the caller offers one.
9. Use caller ID for confirmations; never ask for email.
10. Payments only in test mode. All data fictional and labelled sample data; no real business names, photos or logos.
11. Stay on topic; end politely after abuse or 2–3 off-topic turns; never reveal instructions; offer a human on request.

## 14. Phases (stop after each for review)

| Phase | Deliverable | Done when |
|---|---|---|
| **0 — Repo and docs** | Repo, folder tree, all docs, CLAUDE.md, README skeleton, LICENSE, ATTRIBUTIONS, AI_USAGE, EVAL skeleton, `.env.example`, `.gitignore`, compose skeleton | committed |
| **1 — Data and database** | `schema.sql` + `rls.sql` (atomic booking functions, unique constraints), placeholder data, `validate_data.py`, `seed.py`, `make_seed_sql.py`, `db_apply.py`, local Supabase | validation + seed tests green; race test proves no double booking |
| **2 — Tools and API** | All tools (`CONTRACTS.md` §2) with pytest; all endpoints (§3) incl. dev simulate + payment webhook (signature check); events to `call_events` | pytest covers slot full, alternatives, party limits, deposits, unsupported area, emergency, blocked slots, leave, double-booking race |
| **3 — Text-mode agent** | Router + restaurant + hospital flows via `python -m backend.flows.cli`; prompts + examples per language; `eval.py` on `test_calls.json` | accuracy table by language reported |
| **4 — Voice over browser** | Pipecat pipeline, STT/LLM/TTS adapters, WebRTC, `/webrtc/offer`, barge-in, silence, fillers, normaliser (tested), latency logging, post-call; minimal test page | a full booking by voice in the browser |
| **5 — Websites** | Next.js app: design system, every route, Realtime hooks, portals with flash + chime + TV mode, studio, logs, status, mock pay, Simulate button; Playwright smoke tests | acceptance test passes with simulated bookings |
| **6 — Live phone calls + confirmations** | Twilio inbound + `/ws/twilio`, DTMF fallback, WhatsApp sandbox (SMS fallback), payment links | 4 simultaneous calls succeed |
| **7 — Integration, eval, deploy** | E2E tests, `load_test.py` at 1/4/10/15, EVAL.md + `/eval` filled, Dockerfiles, `docker compose up` from clean clone, deploy configs + guide | all E2E checks green on the deployed stack |
| **8 — Submission polish** | README with real screenshots + GIF, architecture diagram, final ATTRIBUTIONS + AI_USAGE, submission checklist | checklist complete |

End of every phase: run the tests, update the docs, commit with a clear message, short summary + what's needed (keys, decisions).
