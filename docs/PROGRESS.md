# Vaani — progress

Short "phase done" notes so a new session can resume quickly. Details, test counts and decisions per session live in [WORKLOG.md](WORKLOG.md).

| Phase | State | Note |
|---|---|---|
| 0 Repo + docs | done | `d33536a` |
| 1 Data + database | done | local Supabase / RLS / Realtime still unverified on a real Supabase |
| 2 Tools + API | done | `7343662` |
| 3 Text agent + eval | done | PR #1; re-checked on real data (below) |
| Data import | done | branch `data-real-import` |
| 4 Voice over browser | done | branch `phase-4-voice`; live-mic check and hosted DB pending |
| 5 Websites | not in this repo yet | teammates building separately |
| 6–8 | not started | |

## Data import done (23 Nov 2026)
- **Built:** `scripts/import_data.py` (shape-only conversion of Akshit's 9 files + validation), weekday-specific doctor hours, baseline phrase merge, eval clock frozen at 09:00 IST (Python + per-DB `vaani.now_ist`), real-data tests, parser and safety fixes found by the eval.
- **Results:** 231 tests pass, ruff + mypy clean; eval on real data 32/40 first run, 40/40 on 6 runs after fixes (EVAL.md). Merged via PR #2.
- **Open:** self-harm reply (needs approval), no blocked slots / doctor leave in the real data, held-out test calls, Supabase DB, Sarvam key.

## Phase 4 done (23 Nov 2026)
- **Built:** one Pipecat 1.16 pipeline per call (Sarvam STT translit → Silero VAD + Smart Turn → `VaaniBrain` running the Phase 3 Session → normaliser → Sarvam Bulbul TTS), `POST/PATCH /webrtc/offer`, `/voice-test` page, SSE events, silence handler, fillers, barge-in, per-turn latency → `latency` events + `calls.latency_json`, headless probe `backend/eval/voice_probe.py`, `VAANI_DEV_DB=ephemeral` for local runs.
- **Results:** Hindi restaurant and Telugu hospital demo scenarios book correctly by voice (synthetic callers); latency and barge-in in EVAL.md; 295 tests pass; text eval 40/40.
- **Open:** Sarvam credits exhausted (top up to use voice), Supabase DB password (schema/seed not applied to the hosted project), real-mic test, self-harm reply approval, Pipecat Flows FlowManager not used (decision in ARCHITECTURE.md).

## Self-harm reply done (23 Nov 2026)
- Separate gentle reply (Tele-MANAS 14416 / 1-800-891-4416, 112 if in danger) for self-harm words in any call; no booking. `self_harm_phrases` + `self_harm_reply` in `speciality_mapping.json`. 311 tests; eval 40/40. Self-harm matching is exact (fuzzy matched "karna chahta hoon"). Reply text needs a native te/hi review.
