# Vaani — Team and task checklists

Progress and handoffs live in [WORKLOG.md](WORKLOG.md); each phase has a ready prompt in [PHASE_PROMPTS.md](PHASE_PROMPTS.md); agent rules in [../AGENTS.md](../AGENTS.md).

Everyone owns a starting area, but nobody is limited to it. Pick up anything, tick it here in the same commit, and say so in the group chat so two people don't build the same thing.

| Person | Starting area | Suggested first tasks |
|---|---|---|
| **Pranav** | Voice AI + integration lead, captain | Telephony, voice pipeline, router + agents, tools, confirmations; merges everything, deploys |
| **Karthik** | Websites: public side + payments (start from [FRONTEND_PROMPT.md](FRONTEND_PROMPT.md)) | Design system, landing, explore, restaurant + hospital mini-sites, booking status, payment pages + webhook UI |
| **Akshit** | Websites: partner + ops side (start from [FRONTEND_PROMPT.md](FRONTEND_PROMPT.md)) | Partner portals (floor plan, doctor calendar, TV mode, flash + sound), Live Call Studio, call logs, eval page |
| **Rithvik** | Data, evaluation, demo (suggested) | Run the ChatGPT data prompt, validate + seed, test set, eval runs, naturalness ratings, README/deck/video |

**How the work connects:** websites never wait for the voice AI. They read Supabase and write through the backend endpoints in `CONTRACTS.md` §3, and the dev-only "Simulate a call booking" button lets the website team test live updates before calls work. When the voice AI books for real, the same events fire.

## Shared first steps (everyone, ~30 minutes)

- [ ] Confirm the two areas (default Jubilee Hills + Gachibowli) and send the data prompt (`docs/DATA_PROMPT.md`)
- [ ] Agree on the contracts in `docs/CONTRACTS.md`
- [x] Base repo: `data/`, `supabase/`, `CLAUDE.md`, `.env.example`, LICENSE, ATTRIBUTIONS.md (Phase 0)
- [ ] One shared hosted Supabase project for the demo; everyone gets access (local Supabase for dev until then)
- [ ] Twilio trial: verify all 4 phones + 1 spare; everyone joins the WhatsApp sandbox
- [ ] Blind voice test: 5 lines × 3–4 TTS voices × te / hi / en-IN, over a real phone line, 10 raters

## Phase checklists

### Phase 0 — Repo and docs
- [x] Repo, folder tree, `.gitignore`, `pyproject.toml`
- [x] docs/*.md, master-plan.html copied
- [x] CLAUDE.md, README skeleton, LICENSE, ATTRIBUTIONS.md, AI_USAGE.md, EVAL.md skeleton
- [x] `.env.example`, `docker-compose.yml` skeleton

### Phase 1 — Data and database
- [x] `supabase/schema.sql` with atomic `book_table` / `book_appointment` / `cancel_booking`
- [x] `supabase/rls.sql` (anon read-only, phone columns hidden, Realtime publication)
- [x] Placeholder data (9 files) in the DATA_PROMPT schema
- [x] `validate_data.py`, `seed.py`, `make_seed_sql.py`, `db_apply.py`
- [ ] Local Supabase running; schema + seed applied (blocked: Docker Desktop VM not starting)
- [x] Tests: validation, seed expansion, booking rules, 20-caller race

### Phase 2 — Tools and API
- [x] All tools in `CONTRACTS.md` §2 + pytest for every rule
- [x] All website endpoints in §3, dev simulate, mock pay, payment webhook with signature check (voice/Twilio endpoints come in Phases 4 and 6)
- [x] Events into `call_events`

### Phase 3 — Text-mode agent
- [x] Router / restaurant / hospital flows + `python -m backend.flows.cli`
- [x] Prompts + 3 example dialogues per service per language
- [x] `eval.py` with accuracy by language (placeholder data 40/40; real data 32/40 first run → 40/40 after fixes, clock frozen at 09:00)

### Phase 4 — Voice over browser
- [ ] STT / LLM / TTS adapters, pipeline, WebRTC + `/webrtc/offer`
- [ ] Barge-in, silence handler, fillers, normaliser (tested), latency logging
- [ ] Post-call processor; minimal test page

### Phase 5 — Websites
- [ ] Design system + every route in `WEBSITES.md`
- [ ] Realtime hooks, portals with flash + chime + TV mode, studio, logs, status, mock pay
- [ ] Simulate-booking button; Playwright smoke tests; acceptance test with simulated bookings

### Phase 6 — Live phone calls
- [ ] `/twilio/inbound`, `/ws/twilio`, DTMF fallback
- [ ] WhatsApp sandbox confirmations, SMS fallback, payment links
- [ ] 4 simultaneous calls

### Phase 7 — Integration, eval, deploy
- [ ] E2E: Hindi restaurant call → portal + mini-site + WhatsApp < 2 s
- [ ] E2E: Telugu hospital call → fee → paid everywhere; blocked slot refused
- [ ] `load_test.py` at 1/4/10/15; EVAL.md + `/eval` filled
- [ ] Dockerfiles, `docker compose up` from clean clone, deploy configs + guide

### Phase 8 — Submission polish
- [ ] README with real screenshots + GIF, architecture diagram
- [ ] Final ATTRIBUTIONS.md, AI_USAGE.md; submission checklist complete
