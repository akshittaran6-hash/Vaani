# Vaani — Evaluation

Every number here is measured, split by Telugu (te-en), Hindi (hi-en) and Indian English (en-IN), and mirrored on the `/eval` page.

> Status: **Phase 3 text eval done** (numbers below). Voice latency, barge-in, naturalness, load and live sync come in Phases 4–7.

## How we measure

- **`backend/eval/eval.py`** replays the 40 scripted calls in `data/test_calls.json` as text turns through the real flows and tools (fast, no audio) and stores a results table.
- **`backend/eval/load_test.py`** streams recorded audio through N simulated callers (1 / 4 / 10 / 15) and records latency and success.
- **Naturalness:** blind 1–5 ratings by 10 people over real calls.
- **Live sync:** timestamp of `booking_created` vs. first render on the partner portal, mini-site and WhatsApp delivery.

## Targets and results

| Metric | Target | te-en | hi-en | en-IN | All |
|---|---|---|---|---|---|
| Booking accuracy (area, business, doctor, date, time, party size all correct) | ≥ 85–90% | 12/12 (100%) | 9/9 (100%) | 7/7 (100%) | **28/28 (100%)** |
| Expected business in top 3 (calls where the agent searched) | ≥ 90% | 9/10 (90%) | 7/8 (88%) | 6/6 (100%) | **22/24 (92%)** |
| Unsupported area handled | 100% | 2/2 | 2/2 | — | **4/4 (100%)** |
| Emergency → 108/112, no booking | 100% | 1/1 | 1/1 | 1/1 | **3/3 (100%)** |
| Slot full → 2 nearest offered | ≥ 90% | 1/1 | 0/1 | 1/1 | **2/3 (67%)** ¹ |
| FAQ answered from the business's own data | report | 2/2 | 2/2 | — | **4/4 (100%)** |
| Call outcome matches expected (all 40 calls) | report | 16/16 | 14/14 | 10/10 | **40/40 (100%)** |
| Time to first audio (median / slowest) | ~1 s / < 2 s | TBD | TBD | TBD | TBD (Phase 4; text-mode LLM step: median 1.55 s, p95 2.6 s) |
| Stop speaking on interruption | < 0.5 s | | | | TBD |
| Naturalness (blind 1–5, 10 people) | ≥ 4 | TBD | TBD | TBD | TBD |
| Live sync call → portal + mini-site + WhatsApp | < 2 s | | | | TBD |
| Cost per call minute (telephony + STT + LLM + TTS) | report | | | | TBD |

**Phase 3 text eval** (`uv run python -m backend.eval.eval`, 2026-11-22, model `Qwen/Qwen3-30B-A3B-Instruct-2507` on Featherless, JSON action protocol, temperature 0.2, one fresh seeded DB per call). Three consecutive full runs with the final code all scored 40/40:

| Run (IST) | Calls passed | LLM calls | LLM median / p95 | Tokens in / out | Cost |
|---|---|---|---|---|---|
| 20:48 | 40/40 | 158 | 1712 / 2762 ms | 394k / 11k | $0.054 |
| 20:48 | 40/40 | 169 | 1677 / 3005 ms | 436k / 12k | $0.060 |
| 20:51 | 40/40 | 157 | 1550 / 2615 ms | 375k / 10k | $0.052 |

**Read these numbers with care:**
- The 40 calls and the data are the **placeholder set**, and the agent was tuned while looking at them (the first run of the same set scored 23/40; each fix is in the work log). They show the pipeline works end to end in all three languages; they are **not** a held-out accuracy figure. Re-run the eval once the ChatGPT data and fresh test calls from `docs/DATA_PROMPT.md` land.
- It's text in, text out: no speech recognition errors, no audio latency. Phone audio will be harder.
- Much of the reliability comes from code, not the LLM: deterministic guards (emergency, unsupported area, FAQ, OTP redaction), extraction of party size / names / named businesses / days / times from the caller's words, and code-written read-backs. The LLM picks the next step and phrases replies.

¹ In T01 the caller asks "kitne baje available hai?" without naming a time, so the agent reads the free times rather than "the 2 nearest to X". The call still books the right slot; the metric counts it as a miss.

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
| Data integrity | `scripts/validate_data.py` + 15 mutation tests | ✅ placeholder set: 0 errors, 0 warnings |
| Tools enforce every rule | `backend/tests/test_tools_*.py`: slot full → 2 nearest, party limit, deposits, unsupported area, blocked slots, doctor leave, fully booked, past times, ≤ 3 results, 10-way race through the tool runner | ✅ (Phase 2) |
| Emergency phrases never book | every one of the 46 emergency phrases → `emergency`; every one of the 105 speciality phrases → its speciality, none flagged as emergency | ✅ (Phase 2) |
| Blocked slot refused (tool level) | `test_api.py::test_blocked_slot_is_refused_by_the_ai`: portal block → `book_table` returns `BLOCKED` | ✅ (Phase 2); full voice E2E in Phase 7 |
| Read-back = what gets booked | `test_flows_session.py::test_readback_comes_from_code_not_the_llm`; read-backs are built in code from the booking arguments (the LLM once read back 8:30 while asking to book 19:30) | ✅ (Phase 3) |
| No booking without a confirmed read-back | `test_confirm_needs_an_earlier_readback` (needs `propose_*` on an earlier turn, then a yes) | ✅ (Phase 3) |
| LLM can't invent the caller's name | `test_llm_cannot_invent_the_callers_name` (name must appear in the caller's words) | ✅ (Phase 3) |
| Emergency handled without the LLM | `test_emergency_guard_never_calls_the_llm` + 3/3 eval calls | ✅ (Phase 3) |
| OTP / card numbers never stored or sent to the LLM | `test_otp_is_redacted_and_refused` (redacted before transcript, events and LLM) | ✅ (Phase 3) |
| Blocked slot refused by the AI | E2E test (Phase 7) | TBD |
| Booking visible everywhere < 2 s | E2E test (Phase 7) | TBD |
