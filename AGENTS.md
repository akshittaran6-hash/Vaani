# AGENTS.md — rules for every coding agent working on Vaani

This file is for **any** AI coding agent (Claude Code, Codex, Cursor, Copilot, Gemini CLI, Windsurf, …) and the human driving it. Read it fully before doing anything. `CLAUDE.md` holds the same project rules in more detail; if the two ever disagree, stop and ask the human.

## 1. Before you write any code

Read, in this order:

1. `docs/WORKLOG.md` — **what has already been done, by whom, and the latest handoff.** Start from the newest entry.
2. `CLAUDE.md` — stack, contracts summary, hard safety rules, commands.
3. `docs/MASTER_PLAN.md` — the whole project; §14 lists the phases.
4. `docs/PHASE_PROMPTS.md` — the prompt for the phase you're doing (scope, steps, done-when).
5. `docs/CONTRACTS.md` — tables, tools, endpoints, events, data files. **Fixed. Don't change them alone.**
6. Phase-specific docs: `docs/CALL_FLOW.md` (agent/voice), `docs/WEBSITES.md` + `docs/FRONTEND_PROMPT.md` (frontend), `docs/DEMO.md`, `EVAL.md`, `docs/LIMITS.md`.

Then run the checks, so you know the baseline is green before you change anything:

```bash
uv sync
uv run python scripts/validate_data.py
uv run pytest -q
uv run ruff check . && uv run mypy backend scripts
```

## 2. Who works on what

| Area | People | Notes |
|---|---|---|
| Frontend (`frontend/`, Phase 5) | Akshit, Karthik | In progress separately from `docs/FRONTEND_PROMPT.md`. Backend agents don't build pages. |
| Backend phases 3, 4, 6, 7, 8 | Rithvik and Pranav | Pick a phase, record it in `docs/WORKLOG.md` **before** starting so two people don't build the same thing. |

## 3. Git workflow

- **Never commit to `main` directly.** One branch per phase or task: `phase-3-text-agent`, `phase-4-voice`, `fix/<thing>`.
- Small commits with clear messages (`feat:`, `fix:`, `docs:`, `test:`, `chore:`). Open a PR into `main`; another teammate (or Pranav) merges.
- Pull `main` before you start and before you open the PR. Keep `main` green: tests, ruff and mypy must pass on your branch.
- Never force-push to `main`. Never rewrite someone else's history.

## 4. Secrets — non-negotiable

- **Never commit `.env`, API keys, tokens or passwords.** `.env` is git-ignored; `.env.example` lists variable names with empty values.
- Never paste a key into code, docs, tests, logs, commit messages or `docs/WORKLOG.md`. Refer to it by variable name (`LLM_API_KEY`).
- Before every commit: `git diff --cached` and make sure no key-like strings are staged.
- If a key leaks, tell Pranav immediately so it can be rotated.

## 5. The work log (mandatory)

Every agent session **must** keep `docs/WORKLOG.md` up to date, so the next person or agent can continue exactly where you stopped.

- **At the start of a session:** add an entry with status `in progress` (template below). Get the timestamp from the shell with `date "+%Y-%m-%d %H:%M %Z"`, and never guess it.
- **After each meaningful step** (a module finished, tests added, a decision made, a blocker hit): update that entry.
- **At the end of a session** (or when the human says stop): finish the entry with what's done, what isn't, exact test results and the next steps, then commit it together with your code.
- Newest entry at the **top** of the "Entries" section. Don't edit or delete other people's entries; add a correction entry instead.
- Be concrete: file paths, commands, test counts, numbers. "Improved stuff" is not a log entry.

Entry template:

```markdown
### <YYYY-MM-DD HH:MM IST> · Phase <n> · <person> via <agent/tool> · <status: in progress | done | blocked | handed off>
**Branch:** `<branch>` · **Commits:** `<short sha>`, …
**Goal:** one line.
**Done:**
- …
**Files:** `path/a.py` (new), `path/b.md` (updated)
**Tests / checks:** `uv run pytest -q` → N passed · ruff ✓ · mypy ✓ · other numbers (eval accuracy, latency) …
**Decisions:** what you chose and why (and anything that changes a contract, with the docs you updated).
**Blockers / needs from humans:** keys, accounts, decisions.
**Next steps:** numbered list a new agent can start on immediately.
```

## 6. How to work

- **Check current official docs before using a library API** (Context7 or web docs): Pipecat, Pipecat Flows, Supabase, FastAPI, Twilio, Sarvam, Next.js change fast. Don't guess import paths.
- Plan first for anything non-trivial; tell the human the plan before large changes.
- Small, readable modules with type hints (mypy strict) and short comments on non-obvious code.
- Every new rule gets a test. Bookings only through the tools and the Postgres functions (`backend.tools.run_tool`).
- Keep docs in sync in the same commit: if behaviour changes, update `docs/CONTRACTS.md`, `README.md`, `EVAL.md`, `docs/TEAM.md` checklists as relevant. If a fact changes, grep for it and update it everywhere.
- Missing key or account → keep building against mocks, and log the blocker in the work log.
- Tests and eval use **throwaway databases** (`backend/devdb.py`, `backend/tests/conftest.py`). Never point tests or eval at the shared or demo Supabase: they wipe data.

## 7. Safety rules for the product (from CLAUDE.md — never break these)

1. The LLM talks; **code decides**. Availability, party limits, supported areas, booking IDs and payments are validated in tools. Never invent businesses, slots or IDs.
2. At most 3 options read aloud. Greeting always discloses "I'm Vaani, an AI assistant". Never claim to be human.
3. Emergency phrases in hospital calls → "call 108 / 112 immediately", **no booking**. Self-harm words in any call → the gentle Tele-MANAS 14416 / 112 reply, **no booking**. Never diagnose.
4. Never ask for OTP, PIN, CVV, card or account numbers. Use caller ID; never ask for email.
5. Payments test mode only. All data fictional (`is_sample_data: true`).
