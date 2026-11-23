# AI usage

We use AI in two different ways, and we're open about both.

## 1. AI inside the product

- Vaani is an AI voice agent. **Every call starts with a disclosure** — "I'm Vaani, an AI assistant" (in the caller's language) — and Vaani never claims to be human. Callers can ask for a human at any time and get a handoff/callback message.
- The LLM only chooses the words. **Code decides**: availability, party limits, supported areas, booking IDs and payments are checked in tools and in the database. The LLM cannot create a booking a tool rejects.
- Hospital calls never diagnose; emergency phrases get "please call 108 or 112 immediately" and no booking.
- Vaani never asks for OTPs, PINs, CVVs, card or account numbers.
- Call transcripts, outcomes and latency are stored for evaluation and shown in the demo's call logs. All demo businesses and bookings are fictional.

## 2. AI tools used to build Vaani

| Tool | Used for |
|---|---|
| Claude Code (Anthropic) | Planning, scaffolding, writing code, tests and docs together with the team, phase by phase |
| ChatGPT | Generating the final fictional demo data from `docs/DATA_PROMPT.md` |
| Claude Code (placeholder data) | A one-off script produced the first placeholder data set so development wasn't blocked; it now lives on only as the unit-test fixture (`backend/tests/fixtures/placeholder_data/`) |
| Claude Code (data import) | `scripts/import_data.py` converts the generated files to the contract's shape (no content changes except merging a baseline phrase list), then validates; a human reviewed the diff |
| _others added as used_ | |

How we keep it honest:

- **A human on the team reviews all AI-written code** before it is merged, and each phase stops for review before the next begins.
- Tests (pytest, Playwright) and the evaluation in `EVAL.md` check behaviour; we report measured numbers, not claims.
- Library APIs are checked against current official docs rather than taken on trust.
- AI-generated data is validated by `scripts/validate_data.py` and read by native Telugu and Hindi speakers.
- No secrets or personal data are given to AI tools; all demo data is fictional.
