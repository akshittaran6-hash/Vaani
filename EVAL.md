# Vaani — Evaluation

Every number here is measured, split by Telugu (te-en), Hindi (hi-en) and Indian English (en-IN), and mirrored on the `/eval` page.

> Status: **text eval re-run on the real data** (23 Nov 2026, numbers below). Voice latency, barge-in, naturalness, load and live sync come in Phases 4–7.

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
| Time to first audio (median / slowest) | ~1 s / < 2 s | TBD | TBD | TBD | TBD (Phase 4; text-mode LLM step: median 1.53 s, p95 2.2 s) |
| Stop speaking on interruption | < 0.5 s | | | | TBD |
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
| 09:47 | final code (amount guard tightened) | 40/40 | 151 | 1528 / 2232 ms | 377k / 10k | $0.052 |

What the first real-data run found, and the fixes (all with tests):
- **Party size** missed Telugu forms `naluguriki` / `mugguram` / `aaruguriki` and "Change that to four" → stem + suffix rules in `flows/extract.py`.
- **Names**: "Anuvi Selavolu peru meeda pettandi" became "Meeda Pettandi"; the LLM used "Sare" and the *doctor's* name as the caller's → name-before-marker patterns, filler-word and doctor/business-name checks.
- **Safety:** in T05 the LLM booked when the caller only gave a name. A booking now also needs a yes word in the caller's own turn (`Session.caller_said_yes`), checked in code.
- **Safety:** the LLM wrote its own read-back with an invented fee ("fee 1000 rupaye" for a ₹650 doctor). Sentences with a ₹ amount that no tool returned and that isn't the chosen business's / doctor's own figure are now dropped (`Session._verified_amounts`); the guard fired on 1–2 replies per run afterwards.
- **"Parson"** (Hindi spelling of parso) wasn't a day word; FAQ topics lacked wheelchair access, lab, fee and Sunday timings.
- **Short emergency forms**: the real emergency list had only long sentences, so "सीने में दर्द" and "chest pain" weren't caught. `import_data.py` merges the earlier tested phrases (`scripts/data_extras/speciality_base.json`), 166 speciality + 86 emergency phrases in total.

**Read these numbers with care:**
- 32/40 is the honest first-contact number; 40/40 is after fixing what those 8 calls exposed, so it's no longer held-out. A fresh set of 10–20 test calls that nobody has looked at would give a held-out number.
- It's text in, text out: no speech recognition errors, no audio latency. Phone audio will be harder.
- Much of the reliability comes from code, not the LLM: deterministic guards (emergency, unsupported area, FAQ, OTP redaction), extraction of party size / names / named businesses / days / times from the caller's words, code-written read-backs, and the yes / amount checks above. The LLM picks the next step and phrases replies.

¹ All 3 misses (T06, T13, T15) are calls where the caller named a place that is full or too small at the requested time, so the agent's search correctly left it out; each call still ends with the expected outcome.

Earlier, on the placeholder data the agent was built on (22 Nov), three runs scored 40/40 after the first scored 23/40 (work log, Phase 3).

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
| Emergency phrases never book | every emergency phrase → `emergency`; every speciality phrase → its speciality, none flagged as emergency (fixture: 46 + 105; real data: 86 + 166, checked by `test_real_data.py`) | ✅ |
| Blocked slot refused (tool level) | `test_api.py::test_blocked_slot_is_refused_by_the_ai`: portal block → `book_table` returns `BLOCKED` | ✅ (Phase 2); full voice E2E in Phase 7 |
| Read-back = what gets booked | `test_flows_session.py::test_readback_comes_from_code_not_the_llm`; read-backs are built in code from the booking arguments (the LLM once read back 8:30 while asking to book 19:30) | ✅ (Phase 3) |
| No booking without a confirmed read-back | `test_confirm_needs_an_earlier_readback` (needs `propose_*` on an earlier turn, then a yes word in the caller's own turn; a name is not a yes) | ✅ |
| LLM can't state a ₹ amount code didn't give it | `test_llm_cannot_state_an_unverified_amount` | ✅ |
| LLM can't invent the caller's name | `test_llm_cannot_invent_the_callers_name` (name must appear in the caller's words) | ✅ (Phase 3) |
| Emergency handled without the LLM | `test_emergency_guard_never_calls_the_llm` + 3/3 eval calls | ✅ (Phase 3) |
| OTP / card numbers never stored or sent to the LLM | `test_otp_is_redacted_and_refused` (redacted before transcript, events and LLM) | ✅ (Phase 3) |
| Blocked slot refused by the AI | E2E test (Phase 7) | TBD |
| Booking visible everywhere < 2 s | E2E test (Phase 7) | TBD |
