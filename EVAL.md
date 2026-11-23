# Vaani — Evaluation

Every number here is measured, split by Telugu (te-en), Hindi (hi-en) and Indian English (en-IN), and mirrored on the `/eval` page.

> Status: **text eval on the real data** and **first voice measurements** (23 Nov 2026, synthetic callers over local WebRTC, numbers below). Naturalness, load, phone audio and live sync come in Phases 5–7.

## How we measure

- **`backend/eval/eval.py`** replays the 40 scripted calls in `data/test_calls.json` as text turns through the real flows and tools (fast, no audio) and stores a results table.
- **`backend/eval/load_test.py`** streams recorded audio through N simulated callers (1 / 4 / 10 / 15) and records latency and success.
- **Naturalness:** blind 1–5 ratings by 10 people over real calls.
- **Live sync:** timestamp of `booking_created` vs. first render on the partner portal, mini-site and WhatsApp delivery.

## Targets and results

| Metric | Target | te-en | hi-en | en-IN | All |
|---|---|---|---|---|---|
| Booking accuracy (area, business, doctor, date, time, party size all correct) | ≥ 85–90% | 7/7 (100%) | 11/11 (100%) | 6/6 (100%) | **24/24 (100%)** |
| Expected business in top 3 (calls where the agent searched) | ≥ 90% | 6/7 (86%) | 7/9 (78%) | 4/4 (100%) | **17/20 (85%)** ¹ |
| Unsupported area handled | 100% | 2/2 | 2/2 | 1/1 | **5/5 (100%)** |
| Emergency → 108/112, no booking | 100% | 1/1 | 1/1 | 1/1 | **3/3 (100%)** |
| Slot full → 2 nearest offered | ≥ 90% | 2/2 | 1/1 | — | **3/3 (100%)** |
| FAQ answered from the business's own data | report | 2/2 | — | 2/2 | **4/4 (100%)** |
| Call outcome matches expected (all 40 calls) | report | 16/16 | 14/14 | 10/10 | **40/40 (100%)** |
| Time to first audio (median / p90 / slowest) | ~1 s / < 2 s | | | | **1.24 s / 3.2 s / 9.4 s** server · 1.51 s / 3.2 s / 9.7 s caller side ² |
| Stop speaking on interruption | < 0.5 s | | | | **0.24 s** median after the VAD hears the caller (≈ 0.44 s from speech onset); caller side 0.28–1.37 s ³ |
| Naturalness (blind 1–5, 10 people) | ≥ 4 | TBD | TBD | TBD | TBD |
| Live sync call → portal + mini-site + WhatsApp | < 2 s | | | | TBD |
| Cost per call minute (telephony + STT + LLM + TTS) | report | | | | TBD |

**Real-data text eval** (`uv run python -m backend.eval.eval`, 23 Nov 2026, model `Qwen/Qwen3-30B-A3B-Instruct-2507` on Featherless, JSON action protocol, one fresh seeded DB per call, **clock frozen at 09:00 IST** in Python and in every eval database). Data and the 40 test calls are Akshit's set (`data/`, imported with `scripts/import_data.py`); nobody had tuned the agent on it before the first run.

| Run (IST) | Code | Calls passed | LLM calls | LLM median / p95 | Tokens in / out | Cost |
|---|---|---|---|---|---|---|
| 09:34 | Phase 3 agent as merged (first run on the real data) | **32/40** | 189 | 1546 / 3370 ms | 485k / 13k | $0.067 |
| 09:42 | after the fixes below | 40/40 | 154 | 1571 / 2323 ms | 397k / 11k | $0.055 |
| 09:43 | same | 40/40 | 148 | 1470 / 2128 ms | 362k / 10k | $0.050 |
| 09:44 | same | 40/40 | 146 | 1462 / 1981 ms | 361k / 11k | $0.050 |
| 09:46 | amount guard: fixed a false alarm on "₹" | 40/40 | 154 | 1514 / 2155 ms | 396k / 11k | $0.055 |
| 09:47 | amount guard tightened to the chosen doctor | 40/40 | 151 | 1528 / 2232 ms | 377k / 10k | $0.052 |
| 10:00 | final code after PR review (guard trusts only money fields; one shared yes check) | 40/40 | 149 | 1490 / 2235 ms | 366k / 11k | $0.051 |

What the first real-data run found, and the fixes (all with tests):
- **Party size** missed Telugu forms `naluguriki` / `mugguram` / `aaruguriki` and "Change that to four" → stem + suffix rules in `flows/extract.py`.
- **Names**: "Anuvi Selavolu peru meeda pettandi" became "Meeda Pettandi"; the LLM used "Sare" and the *doctor's* name as the caller's → name-before-marker patterns, filler-word and doctor/business-name checks.
- **Safety:** in T05 the LLM booked when the caller only gave a name. A booking now also needs a yes word in the caller's own turn (`Session.caller_said_yes`), checked in code.
- **Safety:** the LLM wrote its own read-back with an invented fee ("fee 1000 rupaye" for a ₹650 doctor). Sentences with a ₹ amount that no tool returned and that isn't the chosen business's / doctor's own figure are now dropped (`Session._verified_amounts`); the guard fired on 1–2 replies per run afterwards. It trusts only money fields in tool results (`*_inr`, fee, deposit, amount, price) and ₹ amounts in answer text, never dates, times, IDs or timings.
- **"Parson"** (Hindi spelling of parso) wasn't a day word; FAQ topics lacked wheelchair access, lab, fee and Sunday timings.
- **Short emergency forms**: the real emergency list had only long sentences, so "सीने में दर्द" and "chest pain" weren't caught. `import_data.py` merges the earlier tested phrases (`scripts/data_extras/speciality_base.json`), 166 speciality + 86 emergency phrases in total (since 23 Nov evening: 78 emergency + 33 self-harm, which get their own Tele-MANAS reply).

**Read these numbers with care:**
- 32/40 is the honest first-contact number; 40/40 is after fixing what those 8 calls exposed, so it's no longer held-out. A fresh set of 10–20 test calls that nobody has looked at would give a held-out number.
- It's text in, text out: no speech recognition errors, no audio latency. Phone audio will be harder.
- Much of the reliability comes from code, not the LLM: deterministic guards (emergency, unsupported area, FAQ, OTP redaction), extraction of party size / names / named businesses / days / times from the caller's words, code-written read-backs, and the yes / amount checks above. The LLM picks the next step and phrases replies.

¹ All 3 misses (T06, T13, T15) are calls where the caller named a place that is full or too small at the requested time, so the agent's search correctly left it out; each call still ends with the expected outcome.

Earlier, on the placeholder data the agent was built on (22 Nov), three runs scored 40/40 after the first scored 23/40 (work log, Phase 3).

## Voice (Phase 4)

Measured with `backend/eval/voice_probe.py`: a synthetic caller (Sarvam TTS voice "rahul", romanised Hindi / Telugu lines) talks to the running server over WebRTC (aiortc, localhost), waits for each reply and records timings from its side; the server logs its own per-turn timings (`latency` events / `calls.latency_json`). Scenarios = the two DEMO.md demos (Hindi restaurant: Dumgalli 8:30 full → 7:00; Telugu hospital: Dr. Navisha full → Dr. Suvin 15:00). Stack: Sarvam saaras:v3 STT (translit) · Silero VAD + Smart Turn v3 · Featherless Qwen3-30B-A3B (JSON actions) · Sarvam Bulbul v3 TTS.

**Bookings by voice:** 9 of the last 10 calls (17:15–17:33 IST) booked the right place, doctor/table, day and time; the 10th stalled on two issues fixed right after (STT wrote "gantalaki" as "bantlaki"; the LLM wrote its own read-back instead of calling `propose_*`, so code had nothing to confirm; nothing wrong was booked). The two runs on the final code: 4/4 correct. Telugu calls that show 15:30 had 15:00 already taken by an earlier run on the same test database; Vaani read back 15:30 and the caller confirmed it.

Per-turn timings (49 turns from those 10 calls; ms):

| Stage | Median | p90 | Slowest | What it covers |
|---|---|---|---|---|
| STT + end of turn | 341 | 1701 | 1704 | caller stops → final transcript and Smart Turn's "done" (p90 = turns where Smart Turn was unsure and waited the 1.5 s cap) |
| Think | 601 | 2152 | 7486 | transcript → first words to TTS: guards and code read-backs take ~5 ms; LLM turns hit the 0.6 s filler |
| TTS first audio | 216 | 237 | 538 | Bulbul streaming |
| **Turn total** | **1237** | 3199 | 9386 | caller stops → Vaani audible (server) |
| Caller side | 1511 | 3163 | 9678 | end of the caller's audio → Vaani's audio heard (adds VAD stop window, WebRTC, jitter buffer) |
| Turns decided by code only | 541 | 594 | 601 | read-back, confirm, guards (9 turns) |
| Greeting | 948 | 1025 | 1633 | connect → greeting heard |

² The slow tail is the LLM provider: in the same hour the text eval showed LLM median 2.1 s and p95 12.3 s (morning: 1.5 s / 2.2 s). Voice now gives up on an LLM step after 4.5 s, retries once, and says a second filler at ~4 s; the slowest turns above were measured before that change. Run-to-run spread is large; treat these as first numbers, not a benchmark.

³ Barge-in: the server measures from the VAD's "caller started" to Vaani's audio stopping: median 236 ms, 17 interruptions, max 608 ms; Silero needs ~0.2 s of speech first. From the caller's side (probe talks over Vaani 1 s into her answer; detected by audio energy): 1018, 279, 978, 1372, 913, 1027 ms, which also includes audio already in flight and the probe's 250 ms silence detector.

Not measured yet: real voices and rooms, phone audio (Phase 6), many calls at once. Sarvam credits ran out at the end of this session (402 `insufficient_quota_error`), which stopped the last run.

## Load test

| Concurrent callers | Median time to first audio | Slowest | Success % |
|---|---|---|---|
| 1 | TBD | TBD | TBD |
| 4 | TBD | TBD | TBD |
| 10 | TBD | TBD | TBD |
| 15 | TBD | TBD | TBD |

## Stack comparisons

_STT / LLM / TTS candidates compared on latency, accuracy and cost go here._

## Verification matrix

| Requirement | How verified | Result |
|---|---|---|
| No double booking under concurrency | `backend/tests/test_db_booking.py`: 20 concurrent callers on one doctor slot and on a restaurant's only 12-seat table | ✅ exactly 1 success, 19 `SLOT_TAKEN` / `SLOT_FULL` (Phase 1, Postgres 15) |
| Booking rules enforced in the database | same file: slot full, blocked, party limit, doctor leave, past time, unknown business, cancel frees slot | ✅ (Phase 1) |
| Data integrity | `scripts/validate_data.py` + 16 mutation tests (incl. weekday-specific hours) | ✅ real set: 0 errors, 7 warnings (no blocked slots, no doctor on leave, scenario mix) |
| Real data still gives the demo scenarios | `backend/tests/test_real_data.py`: top 3 in Jubilee Hills, Dumgalli 19:00 only, ₹300 deposit, Pulao Pankthi full for 6, Dr. Navisha full / Dr. Suvin from 15:00, real FAQs | ✅ |
| Tools enforce every rule | `backend/tests/test_tools_*.py`: slot full → 2 nearest, party limit, deposits, unsupported area, blocked slots, doctor leave, fully booked, past times, ≤ 3 results, 10-way race through the tool runner | ✅ (Phase 2) |
| Emergency phrases never book | every emergency phrase → `emergency`; every speciality phrase → its speciality, none flagged as emergency (fixture: 42 emergency + 29 self-harm + 105; real data: 78 emergency + 33 self-harm + 166, checked by `test_real_data.py`) | ✅ |
| Blocked slot refused (tool level) | `test_api.py::test_blocked_slot_is_refused_by_the_ai`: portal block → `book_table` returns `BLOCKED` | ✅ (Phase 2); full voice E2E in Phase 7 |
| Read-back = what gets booked | `test_flows_session.py::test_readback_comes_from_code_not_the_llm`; read-backs are built in code from the booking arguments (the LLM once read back 8:30 while asking to book 19:30) | ✅ (Phase 3) |
| No booking without a confirmed read-back | `test_confirm_needs_an_earlier_readback` (needs `propose_*` on an earlier turn, then a yes word in the caller's own turn; a name is not a yes) | ✅ |
| LLM can't state a ₹ amount code didn't give it | `test_llm_cannot_state_an_unverified_amount` | ✅ |
| LLM can't invent the caller's name | `test_llm_cannot_invent_the_callers_name` (name must appear in the caller's words) | ✅ (Phase 3) |
| Self-harm → Tele-MANAS 14416 + 112, no booking, in any call | `test_self_harm_guard_any_service` (te/hi/en, even mid restaurant call, no LLM call) + every one of the 33 real self-harm phrases → `self_harm` (`test_real_data.py`); validator requires 14416 and 112 in every language | ✅ |
| Emergency handled without the LLM | `test_emergency_guard_never_calls_the_llm` + 3/3 eval calls | ✅ (Phase 3) |
| OTP / card numbers never stored or sent to the LLM | `test_otp_is_redacted_and_refused` (redacted before transcript, events and LLM) | ✅ (Phase 3) |
| Blocked slot refused by the AI | E2E test (Phase 7) | TBD |
| Booking visible everywhere < 2 s | E2E test (Phase 7) | TBD |
