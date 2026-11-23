# Vaani — Contracts

These names and shapes are the agreement between the voice AI, the backend and the websites. **Change them only with the whole team**, and update this file, `CLAUDE.md` and the code in the same commit.

Conventions used everywhere:

- Dates are `YYYY-MM-DD` in **IST (Asia/Kolkata)**; times are 24h `HH:MM` strings in JSON and `time` in Postgres.
- Timestamps are ISO 8601 with offset, e.g. `2026-11-23T20:12:05+05:30`.
- Languages: `te`, `hi`, `en` (Indian English). Language mixes in data/eval: `te-en`, `hi-en`, `en-IN`.
- IDs: areas `jubilee_hills`; restaurants `r_jh_01`; hospitals `h_gb_01`; doctors `d_gb_01_derm_1`; tables `T1…Tn`; bookings `VN-1234` (4 digits); calls `c_<uuid12>`; payments `pay_<uuid12>`.
- Demo areas are set by `DEMO_AREA_1` / `DEMO_AREA_2` (default `jubilee_hills`, `gachibowli`).

---

## 1. Database tables (Supabase Postgres)

Source of truth: `supabase/schema.sql` (Phase 1). `[]` = Postgres array, `{}` = `jsonb`.

### areas
| column | type | notes |
|---|---|---|
| area_id | text PK | `jubilee_hills` |
| name_en, name_te, name_hi | text | te in Telugu script, hi in Devanagari |
| aliases | text[] | lower-case spellings + common mis-hearings, used by `resolve_area` fuzzy match |
| lat, lng | double precision | approximate area centre (map pin) |
| nearby_unsupported_areas | text[] | real neighbouring area names; recognised so we reply politely |
| unsupported_area_reply | {} | `{"te": "...", "hi": "...", "en": "..."}` |
| is_sample_data | boolean | always true |

### restaurants
| column | type | notes |
|---|---|---|
| restaurant_id | text PK | `r_jh_01` |
| slug | text unique | `spice-garden-jubilee-hills` (derived from name + area by seed if absent) |
| name, name_spoken_te, name_spoken_hi | text | |
| name_aliases | text[] | short forms / mis-hearings |
| area_id | text FK → areas | |
| address | text | `<fictional landmark>, Jubilee Hills` |
| cuisines | text[] | |
| food_type | text | `veg` \| `non-veg` \| `both` |
| rating | numeric(2,1) | 3.8–4.8, labelled "sample" in UI |
| price_for_two_inr | integer | |
| highlight | text | one neutral line |
| popular_dishes | text[] | 3–5 |
| opening_hours | {} | `{"mon": ["12:00-15:30","19:00-23:00"], …, "sun": [...]}`; `[]` = closed |
| features | {} | `{"parking","outdoor_seating","kids_friendly","wheelchair_access","live_music"}` booleans |
| booking_rules | {} | `{"max_party_size": 12, "deposit_required_for_party_size_at_least": 8, "deposit_inr": 500, "cancellation": "..."}` |
| slot_length_minutes | integer | how long a table is held (90) |
| faqs | {} | `[{"q","a_en","a_te","a_hi"}]` |
| phone | text | placeholder `DEMO-R-001` |
| accent_color | text | hex, derived from name by seed if absent |
| is_sample_data | boolean | |

### restaurant_tables
`(restaurant_id FK, table_id)` PK, `capacity integer` (2/4/6/8).

### restaurant_slots
| column | type | notes |
|---|---|---|
| restaurant_id, date, time | PK | one row per bookable start time per day |
| booked_table_ids | text[] | tables already taken for that start time |
| blocked | boolean | staff blocked it → AI must treat it as full |

Bookable start times (fixed for the demo): lunch `12:30 13:00 13:30 14:00`, dinner `19:00 19:30 20:00 20:30 21:00 21:30`, kept only when the start falls inside an opening range (`open <= start < close`).

Demo simplifications: **each start time is an independent seating** (a table booked at 20:00 doesn't block 20:30), and **one party sits at one table**, so `max_party_size` can't exceed the largest table.

### hospitals
`hospital_id` PK (`h_gb_01`), `slug` unique, `name`, `name_spoken_te`, `name_spoken_hi`, `name_aliases[]`, `area_id` FK, `type` (`multi-speciality hospital` \| `clinic`), `address`, `rating`, `highlight`, `specialities[]`, `facilities {}` (`emergency_24x7, pharmacy, lab, ambulance, cashless_insurance, wheelchair_access`), `opd_hours {}` (`{"mon": "09:00-20:00", "sun": "" }`, empty = closed), `languages_spoken[]`, `faqs {}`, `phone`, `accent_color`, `is_sample_data`.

Specialities (closed list): General Medicine, Dermatology, Gynecology, Pediatrics, Orthopedics, ENT, Cardiology, Dental, Ophthalmology.

### doctors
`doctor_id` PK, `hospital_id` FK, `name`, `name_spoken_te`, `name_spoken_hi`, `gender` (`female`\|`male`), `speciality`, `qualification`, `experience_years`, `languages[]`, `consultation_fee_inr`, `schedule {}` (`{"mon": "10:00-13:00", "sat": "10:00-14:00"}`, days absent = not working), `slot_length_minutes` (15), `on_leave_dates date[]`, `is_sample_data`.

### doctor_slots
`(doctor_id, date, time)` PK, `status` = `free` \| `booked` \| `blocked`. One row per slot inside the schedule for the next 7 days.

### speciality_map
`id` serial PK, `phrase`, `lang` (`te`\|`hi`\|`en`), `speciality` (null for emergencies), `is_emergency boolean`.

### bookings
| column | type | notes |
|---|---|---|
| booking_id | text PK | `VN-\d{4}`, generated in the DB booking function |
| service | text | `restaurant` \| `hospital` |
| business_id | text | restaurant_id or hospital_id |
| doctor_id | text FK null | hospital only |
| date, time | date, time | |
| party_size | integer null | restaurant only |
| table_id | text null | restaurant only |
| name | text | caller's name |
| phone | text | caller ID (E.164); **never exposed to anon** |
| language | text | `te` \| `hi` \| `en` |
| source | text | `vaani_call` \| `web` \| `walk_in` |
| status | text | `confirmed` \| `pending_payment` \| `paid` \| `arrived` \| `checked_in` \| `cancelled` |
| amount_due_inr | integer null | deposit or consultation fee |
| call_id | text null | links to the call that made it |
| created_at, updated_at | timestamptz | |

Double-booking is impossible: partial unique indexes on `(business_id, date, time, table_id)` and `(doctor_id, date, time)` where `status <> 'cancelled'`, and bookings are only created through the Postgres functions below, which lock the slot row (`select … for update`).

| Function | Returns | Raises (`message` = code, `hint` = explanation) |
|---|---|---|
| `book_table(restaurant_id, date, time, party_size, name, phone, language='en', source='vaani_call', call_id=null)` | `booking_id, table_id, deposit_needed, deposit_inr` — smallest free table that fits; status `pending_payment` + `amount_due_inr` when a deposit applies, else `confirmed` | `UNKNOWN_BUSINESS`, `PARTY_TOO_LARGE`, `MISSING_DETAILS`, `INVALID_TIME` (past, or not a bookable time), `BLOCKED`, `SLOT_FULL` |
| `book_appointment(doctor_id, date, time, name, phone, language='en', source='vaani_call', call_id=null)` | `booking_id, fee_inr, hospital_id` — status `pending_payment` with the fee due | `UNKNOWN_DOCTOR`, `DOCTOR_ON_LEAVE`, `MISSING_DETAILS`, `INVALID_TIME`, `BLOCKED`, `SLOT_TAKEN` |
| `cancel_booking(booking_id)` | the booking row; frees the table / doctor slot; idempotent | `UNKNOWN_BOOKING` |
| `vaani_today()`, `vaani_now_ist()` | today's date / now in IST, used by the seed and the functions; both honour an optional `vaani.now_ist` setting, which only the eval sets (per throwaway database) to freeze the clock at 09:00 | — |

Only the service role can execute the booking functions.

Anon (frontend) reads `bookings` through **column-level grants that leave out `phone`**. Supabase Realtime strips columns the subscriber can't select, so live updates never carry phone numbers either.

### payments
`payment_id` PK, `booking_id` FK, `amount_inr`, `provider` (`razorpay`\|`stripe`\|`mock`), `provider_ref`, `status` (`created`\|`paid`\|`failed`\|`refunded`), `created_at`, `updated_at`.

### calls
`call_id` PK, `channel` (`phone`\|`web`), `direction` (`inbound`\|`outbound`), `from_number`, `started_at`, `ended_at`, `language text[]`, `services_used text[]`, `transcript {}` (`[{"ts","speaker":"caller|vaani","lang","text"}]`), `outcome_json {}` (§5), `tool_timeline {}` (`[{"ts","tool","args","result","summary","ms"}]`), `latency_json {}` (`{llm_median, llm_p95, llm_calls, per_step_ms, per_step_model, voice_turns: [§4 latency rows], barge_in_ms: [..], tokens_in, tokens_out}`), `recording_url`, `summary` (2 lines).

The row is inserted at `call_started` and completed by the post-call processor.

### call_events
`id` bigserial PK, `call_id` FK → calls, `ts` timestamptz, `type` (§4), `payload {}`.

### Row-level security
- RLS on for every table. The **service role** (FastAPI only) writes.
- **anon** can `select`: areas, restaurants, restaurant_tables, restaurant_slots, hospitals, doctors, doctor_slots, speciality_map, payments (no provider secrets stored), call_events (the backend masks phone numbers in payloads), and `bookings` / `calls` without their `phone` / `from_number` columns.
- Realtime publication `supabase_realtime`: bookings, restaurant_slots, doctor_slots, payments, calls, call_events.

---

## 2. Tools (voice AI)

Implemented in `backend/tools/` (registry: `backend.tools.REGISTRY`; argument models double as the LLM's JSON schemas). Every call goes through `run_tool(ctx, name, args)`, which validates the args, runs the tool, appends `{ts, tool, args, result, summary, ms}` to the call's tool timeline and emits a `tool_called` event `{tool, summary, ms, ok}` when the context has a `call_id`.

Every result has `"ok"`. Errors look like `{"ok": false, "error": "<CODE>", "message": "...", ...extra}` so the flow can speak a natural reply. Dates are `YYYY-MM-DD`, times `HH:MM`; dates must fall in today … today + 6 (IST), else `DATE_OUT_OF_RANGE` (with `earliest` / `latest`). Common codes: `INVALID_ARGS`, `UNKNOWN_TOOL`, `UNSUPPORTED_AREA` (with `supported`), `UNKNOWN_BUSINESS`, `UNKNOWN_DOCTOR`, `UNKNOWN_BOOKING`, `MISSING_DETAILS`.

`phone` is never asked from the caller: booking tools take it from the call context (caller ID). The LLM may omit it.

| Tool | Args | Returns (ok) | Rules enforced in code |
|---|---|---|---|
| `resolve_area` | `text` | `{"area_id", "name"}` or `{"unsupported": true, "heard", "supported": [area_id,…], "reply": {te,hi,en}}` | exact alias/name match (any script) inside the utterance first; known nearby areas → unsupported; then rapidfuzz WRatio ≥ 85 on aliases of 4+ chars |
| `search_restaurants` | `area_id, party_size, date, time?, cuisine?, food_type?` (`veg`\|`non-veg`) | `{"results": [{restaurant_id, name, rating, highlight, cuisines, food_type, free_times}]}` — ≤ 3, by rating; empty results add `reason` (`party_too_large`\|`no_availability`) | demo area only; party ≤ max_party_size; a free fitting table on that date (and at `time` if given); `veg` includes `both`; cuisine matches cuisines, dishes or highlight |
| `get_restaurant_slots` | `restaurant_id, date, party_size, time?` | `{"free": [...], "requested", "requested_full", "nearest": [2 times]}` | blocked = full; a table with capacity ≥ party must be free; past times today hidden; `nearest` only when the requested time is full |
| `book_table` | `restaurant_id, date, time, party_size, name, phone?` | `{"booking_id", "table_id", "deposit_needed", "deposit_inr"}`; emits `booking_created` | atomic `book_table()`; `SLOT_FULL`, `BLOCKED`, `PARTY_TOO_LARGE` (with `max_party_size`), `INVALID_TIME` |
| `map_speciality` | `text, lang?` | `{"speciality", "matched"}` or `{"emergency": true, "matched", "reply"}` or `{"emergency": true, "self_harm": true, "matched", "reply"}` or `{"unknown": true, "specialities"}` | self-harm phrases checked **first** (reply = `self_harm_reply`: Tele-MANAS 14416 / 1-800-891-4416 + 112), then emergency phrases (exact, then ≥ 90 on same-length word windows); then longest exact phrase / department name; then fuzzy ≥ 88 |
| `search_hospitals` | `area_id, speciality, date?` | `{"results": [{hospital_id, name, rating, highlight, doctor_id, doctor_name, fee_inr, next_free: {date, time}, window}]}` — ≤ 3, by rating | demo area only; speciality from the closed list; per hospital the doctor with the earliest free slot from `date` (default today), skipping leave days, blocks and past times |
| `get_doctor_slots` | `doctor_id, date` | `{"free", "on_leave", "fully_booked", "next_free_date", "next_free_time"?}` | leave dates (live from the DB), blocked slots, past times |
| `book_appointment` | `doctor_id, date, time, name, phone?` | `{"booking_id", "fee_inr", "hospital_id"}`; emits `booking_created` | atomic `book_appointment()`; `SLOT_TAKEN`, `BLOCKED`, `DOCTOR_ON_LEAVE`, `INVALID_TIME` |
| `answer_faq` | `business_id, question, lang?` | `{"answer", "lang", "question_matched"}` or `{"unknown": true}` | only that business's FAQs: multilingual topic keywords + token-set similarity; never invents |
| `send_confirmation` | `booking_id, channel?` (`whatsapp` default \| `sms`) | `{"status": "sent"\|"failed", "channel", "message"?}` | sends to the booking's phone (caller ID); WhatsApp → SMS fallback; card format in WEBSITES.md, with the test pay link when a deposit/fee is due |
| `create_payment_link` | `booking_id` | `{"url", "amount_inr", "payment_id", "mode": "test"}` | amount from the booking, never from the LLM; one open payment per booking; `NOTHING_TO_PAY`, `ALREADY_PAID` |
| `switch_service` | `to` (`restaurant`\|`hospital`), `reason?` | `{"service"}`; emits `agent_switched` | name/phone/language carry over (CallContext, Phase 3) |
| `transfer_to_human` | `reason?` | `{"callback_requested": true}` | logged on the timeline for a callback |
| `end_call` | `reason?` | `{"end": true}` | the flow speaks goodbye and ends the pipeline |

---

## 3. Backend endpoints (FastAPI)

`uv run uvicorn backend.api.app:app --port 8000`. Writes go through these endpoints; the backend connects to Postgres directly with `SUPABASE_DB_URL` (the owner role, which bypasses RLS like the service key). Errors are `{"detail": {"error": "<CODE>", "message"}}` with 400 / 401 / 403 / 404 / 409 / 501 / 503.

Partner actions need header **`X-Partner-Passcode`**: a per-business 6-digit demo code derived from `PARTNER_PASSCODE_SECRET` (`uv run python scripts/partner_passcodes.py` prints them).

| Method & path | Purpose | Body / query | Response |
|---|---|---|---|
| `GET /health` | liveness | — | `{"ok", "version", "db"}` |
| `GET /api/businesses?area=&type=` | explore, mini-sites | `type` = `restaurant`\|`hospital` | `[{type, id, ...catalogue fields}]` (hospitals include `doctors`); no phone |
| `GET /api/restaurants/{id}/slots?date=` | mini-site widget, portal | | `{restaurant_id, date, in_window, slots: [{time, free_tables, total_tables, blocked, past}]}` |
| `GET /api/doctors/{id}/slots?date=` | hospital widget, portal | | `{doctor_id, date, on_leave, slots: [{time, status, past}]}` |
| `GET /api/bookings/{id}` | status page | | booking without `phone` + `phone_masked` + `payments: [...]` |
| `GET /api/partners/{id}/bookings?date=` | partner portals | passcode | `[booking + payment_status]` (phone masked) |
| `PATCH /api/bookings/{id}` | portal / status page | `{"status": "arrived"\|"checked_in"\|"cancelled"}` | booking. `arrived` (restaurants) / `checked_in` (hospitals) need the passcode; `cancelled` frees the slot and needs none (status page; demo limit) |
| `POST /api/slots/block` | portal | `{"business_id", "doctor_id"?, "date", "time"?, "all_day"?, "blocked": true}` + passcode | `{"ok", "updated"}`. Restaurant: slot(s) blocked → the AI treats them as full. Hospital: needs `doctor_id`; booked slots are never touched |
| `POST /api/doctors/{id}/leave` | hospital portal | `{"date", "on_leave": bool}` + passcode | `{"ok", "on_leave_dates"}` |
| `POST /api/payments/webhook` | payment provider | raw JSON; `mock`: `{"event": "payment.paid", "payment_id", "provider_ref"?}` signed `X-Vaani-Signature: hex(HMAC-SHA256(PAYMENT_WEBHOOK_SECRET, body))` | `{"ok", "booking_status", "already_paid"}`; idempotent; emits `payment_updated` for call bookings. 401 bad signature, 503 no secret, 501 for razorpay/stripe until Phase 6 |
| `POST /api/payments/{booking_id}/mock-pay` | "Pay (test)" button on `/pay/[booking_id]` | — | same path as a paid webhook; only when `PAYMENT_PROVIDER=mock` |
| `POST /api/dev/simulate-booking` | website testing; only if `DEV_SIMULATE=true` (else 404) | `{"business_id", "doctor_id"?, "date"?, "time"?, "party_size"?, "name"?, "language"?}` | `{call_id, booking, confirmation, timeline}`; books through the real tools, so it emits exactly a call's events |
| `POST /webrtc/offer` | "Talk to Vaani" button | `{"sdp", "type": "offer", "pc_id"?, "request_data"?: {"phone"?: "+91…"}}` (Pipecat SmallWebRTC shape; `requestData` also accepted) | `{"sdp", "type": "answer", "pc_id"}`; the call's pipeline starts in the background. 503 `VOICE_NOT_CONFIGURED` without `SARVAM_API_KEY`, 503 `BUSY` above `MAX_WEB_CALLS` |
| `PATCH /webrtc/offer` | Pipecat JS client (trickle ICE) | `{"pc_id", "candidates": [{"candidate", "sdp_mid", "sdp_mline_index"}]}` | `{"ok": true}` |
| `GET /voice/events/{pc_id}` | `/voice-test` page | `pc_id` URL-encoded (it contains `#`) | Server-Sent Events: `{"type", "payload"}` for every §4 event of that call, then `call_closed`. In-process only; the websites use Supabase Realtime |
| `GET /voice-test` | developers | — | minimal browser test page (mic, live transcript, latency, agent activity) |
| `POST /twilio/inbound` | Twilio voice webhook | Twilio form | TwiML `<Connect><Stream url="{PUBLIC_WS_URL}/ws/twilio"/></Connect>` (Phase 6) |
| `WS /ws/twilio` | Twilio Media Streams | — | Pipecat Twilio serializer (Phase 6) |

---

## 4. Realtime events (`call_events.type`)

```json
{"call_id":"c_123","ts":"2026-11-23T20:12:05+05:30","type":"tool_called",
 "payload":{"tool":"search_restaurants","summary":"Searched restaurants → 3 matches in Jubilee Hills (6 people, tomorrow)"}}
```

| type | payload |
|---|---|
| `call_started` | `{channel, from_masked, simulated?}` |
| `language_detected` | `{lang, confidence, via: "speech"\|"dtmf"\|"simulated"}` |
| `agent_switched` | `{from?, to, reason?}` (`router`\|`restaurant`\|`hospital`) |
| `slot_filled` | `{slot, value}` (area_id, date, time, party_size, speciality, name, business_id, doctor_id) |
| `tool_called` | `{tool, summary, ms, ok}` |
| `booking_created` | `{booking_id, service, business_id, date, time, party_size?, table_id?, doctor_id?, language}` |
| `payment_updated` | `{booking_id, payment_id, status}` |
| `call_ended` | `{outcome, duration_s, booking_id?}` |
| `transcript` | `{speaker, lang, text, final: bool}` — live transcript lines for the Studio |
| `latency` | `{turn, stt, llm_first_token, tts_first_audio, turn_total}` (ms). Voice calls: `stt` = end of the caller's speech → final transcript and end-of-turn decision; `llm_first_token` = transcript → first words handed to TTS (guards, LLM or filler); `tts_first_audio` = → first TTS audio; `turn_total` = end of speech → first audio |

`transcript` and `latency` are additions for the Live Call Studio; the first eight are the fixed list.

---

## 5. Outcome JSON (every call)

```json
{"call_id":"c_123","language":["hi","en"],"service":"restaurant","intent":"book",
 "slots":{"area_id":"jubilee_hills","business_id":"r_jh_01","doctor_id":null,"speciality":null,"date":"2026-11-23","time":"20:30","party_size":6,"name":"Pranav"},
 "outcome":"booked","booking_id":"VN-4821",
 "latency_ms":{"stt":0,"llm_first_token":0,"tts_first_audio":0,"turn_median":0}}
```

- `service`: `restaurant` \| `hospital` \| `null`
- `intent`: `book` \| `info` \| `unsupported_area` \| `emergency` \| `human` \| `other`
- `outcome`: `booked` \| `offered_alternatives` \| `declined_unsupported_area` \| `redirected_emergency` \| `answered_faq` \| `transferred` \| `abandoned` \| `no_availability`

---

## 6. Environment variables

See `.env.example` (kept in sync with this list).

| Variable | Used by | Notes |
|---|---|---|
| TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER, TWILIO_WHATSAPP_FROM | backend | trial account; WhatsApp sandbox sender |
| SARVAM_API_KEY | backend | STT (+ TTS when `TTS_PROVIDER=sarvam`) |
| STT_PROVIDER | backend | `sarvam` (default) \| `deepgram` \| `whisper` |
| LLM_API_KEY, LLM_BASE_URL, LLM_MODEL | backend | any OpenAI-compatible API. `LLM_MODEL` may list several models, tried in order (`qwen/qwen3.8-27b@none,openai/gpt-oss-20b@low,…`; `@x` = that model's `reasoning_effort`): on Groq's free tier each model has its own 8K tokens/min budget |
| LLM_REASONING_EFFORT | backend | sent as `reasoning_effort` when set (`low` for gpt-oss: faster) |
| LLM_FALLBACK_BASE_URL, LLM_FALLBACK_MODEL, LLM_FALLBACK_API_KEY | backend | optional second provider, used when the first fails or returns 429 (primary skipped for 30 s after a 429) |
| TTS_PROVIDER, TTS_API_KEY | backend | `sarvam` (default) \| `elevenlabs` \| `azure` \| `google` |
| SUPABASE_URL, SUPABASE_SERVICE_KEY | backend | Supabase API (Storage for recordings, Phase 4+); service key never reaches the browser |
| SUPABASE_DB_URL | backend, scripts | Postgres connection string: the backend's pool (use the pooler URL when hosted) and `db_apply.py` / `seed.py` (these **wipe and reload** the database) |
| PARTNER_PASSCODE_SECRET | backend | derives the per-business demo passcodes (default `vaani-demo`) |
| VAANI_TEST_DB_URL | tests | optional throwaway Postgres for DB tests (tests wipe it); unset = tests start their own temporary cluster |
| NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY | frontend | read-only under RLS |
| NEXT_PUBLIC_BACKEND_URL | frontend | FastAPI base URL |
| PAYMENT_PROVIDER, PAYMENT_KEY_ID, PAYMENT_KEY_SECRET, PAYMENT_WEBHOOK_SECRET | backend | `mock` \| `razorpay` \| `stripe`, test mode only |
| PUBLIC_BASE_URL | backend | site URL used in WhatsApp links (`<site>/b/VN-4821`) |
| PUBLIC_WS_URL | backend | public `wss://` base for Twilio (ngrok locally) |
| DEMO_AREA_1, DEMO_AREA_2 | backend, scripts | default `jubilee_hills`, `gachibowli` |
| DEV_SIMULATE | backend, frontend | enables `/api/dev/simulate-booking` |
| STT_MODEL, STT_MODE | backend | Sarvam STT model (`saaras:v3`) and mode (`translit` = romanised te/hi, what the parsers expect) |
| TTS_MODEL, TTS_VOICE | backend | Sarvam Bulbul model (`bulbul:v3`) and voice (`priya`), one voice for te / hi / en-IN |
| SILENCE_TIMEOUT_S, FILLER_AFTER_S, TURN_MAX_SILENCE_S | backend | voice timing: silence check after 5 s (twice, then goodbye); filler if the reply isn't ready after 0.6 s; longest wait when Smart Turn thinks the caller isn't done (1.5 s) |
| LLM_VOICE_TIMEOUT_S, LLM_VOICE_RETRIES | backend | voice calls only: per-step LLM timeout (4.5 s) and retries (1), then an apology line; text mode keeps 25 s × 2 |
| WEB_CALLER_PHONE | backend | caller number for browser calls (no caller ID) unless the page sends one |
| MAX_WEB_CALLS | backend | most concurrent browser calls (default 10); beyond it `POST /webrtc/offer` answers 503 `BUSY` |
| VAANI_DEV_DB | backend | `ephemeral` = throwaway local Postgres when `SUPABASE_DB_URL` is empty (local voice testing only) |

---

## 7. Data files (`data/`)

Nine JSON files, all records `"is_sample_data": true`. Generated by a teammate (Akshit) with `docs/DATA_PROMPT.md` and imported with `uv run python scripts/import_data.py <folder>`, which only fixes shape (see its docstring: drops row-level `is_sample_data`, list-shaped `areas.json`, `mappings` → `phrases`, derives `slug` / `accent_color` / `scenario`, merges the baseline phrases in `scripts/data_extras/speciality_base.json`). The original placeholder set lives on as the unit-test fixture in `backend/tests/fixtures/placeholder_data/`. `scripts/validate_data.py` must pass and `scripts/seed.py` must load them with no code changes.

| File | Shape | Maps to |
|---|---|---|
| `areas.json` | `[area]` (§1 areas) | areas |
| `restaurants.json` | `[restaurant]` with embedded `"tables": [{table_id, capacity}]` | restaurants + restaurant_tables |
| `restaurant_availability.json` | `[{restaurant_id, day_offset, time, booked_table_ids[], blocked?}]` — **only slots that are already (partly) booked or blocked**; every other bookable time is free | restaurant_slots |
| `hospitals.json` | `[hospital]` | hospitals |
| `doctors.json` | `[doctor]` with optional `on_leave_day_offsets: [int]` | doctors |
| `doctor_availability.json` | `[{doctor_id, day_offset, booked_times[], blocked_times?[]}]` — only exceptions; other slots in the schedule are free | doctor_slots |

**Weekday rule.** `day_offset` lands on a different weekday depending on the seed date, so restaurants are open every day and every doctor referenced in `doctor_availability.json` or `test_calls.json` works all 7 days. Hours **may differ by weekday** (e.g. a later close on Saturday): free slots are generated from the real weekday of each seeded date, and every booked/blocked exception or expected test-call time must be a slot on **every** weekday (`every_day_times()` in `backend/catalog/schedule.py`). `validate_data.py` enforces this; `seed.py` skips (and reports) any exception that doesn't fall inside that day's hours.
| `speciality_mapping.json` | `{"phrases": [{phrase, lang, speciality}], "emergency_phrases": [{phrase, lang}], "emergency_reply": {te, hi, en}, "self_harm_phrases"?: [{phrase, lang}], "self_harm_reply"?: {te, hi, en}}`. `self_harm_reply` must mention Tele-MANAS 14416 and 112; `import_data.py` moves suicide/self-harm phrases out of `emergency_phrases` | speciality_map (self-harm phrases stored with `is_emergency = true`) |
| `test_calls.json` | `[{test_id, service, language_mix, scenario, caller_turns[], expected{intent, area_id, business_id, speciality, doctor_id, day_offset, time, party_size, outcome}}]` | eval only |
| `agent_phrases.json` | `[{key, "te-en": [3], "hi-en": [3], "en-IN": [3]}]` with `{placeholders}` | loaded by flows |

`day_offset` 0–6 is relative to "today" in IST at seed time; `seed.py` turns it into real dates so the demo always has current slots.
