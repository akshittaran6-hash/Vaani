# Vaani — Costs, limits and known limits

Figures checked against provider pages while writing the master plan (22 Nov 2026). Re-check before the demo; providers change them.

## Costs and provider limits

| Item | Limit / cost | What we do |
|---|---|---|
| Twilio trial credit | $15 preloaded | Covers number, calls, WhatsApp/SMS for the demo |
| Twilio trial voice | 75 voice minutes total, 10 minutes per call, max 5 calls at once | Daily testing via browser calls; phone minutes for the demo |
| Twilio trial numbers | Calls/messages only to verified numbers (up to 5); a short trial message plays first | Verify 4 team phones + 1 spare |
| Twilio trial number country | US number → calling it from India is an international call | Browser calls for most testing; budget phone minutes |
| Twilio after upgrading | New individual accounts start at 3 concurrent calls; more needs an approved business profile | Stay on trial; describe scaling in README |
| SMS to India | Paid per message; may be filtered under India's DLT rules | WhatsApp sandbox first, SMS fallback, status page always |
| LLM concurrency | Plan-dependent (e.g. Featherless Basic = 2 concurrent, Premium = 4) | Dev on any API; use a higher-concurrency API for 4+ live calls |
| STT / TTS (Sarvam etc.) | Usage-priced, rate-limited | Check at signup; measure ₹ per minute in `EVAL.md` |
| ChatGPT Plus / Claude Pro | No API access for the running app | Build tools only |

Cost per call minute (telephony + STT + LLM + TTS) is measured and reported in `EVAL.md`.

## Known limits (copy into README)

- Twilio trial: US number, verified callers only, max 5 calls at once, 75 minutes total, 10 minutes per call.
- 4 real phone calls at once in the demo; 10–15 concurrent shown via browser calls and the load test.
- 2 areas and 20 fictional businesses; production needs partner onboarding or booking-system integrations.
- Telugu, Hindi and Indian English are tested most; Tamil, Kannada and Malayalam are "supported, being tuned".
- Phone-line audio (8 kHz) lowers speech-recognition accuracy compared with browser calls.
- WhatsApp Business Calling is in beta in India and needs a verified business, so it isn't built yet.
- SMS to India may be filtered (DLT); WhatsApp sandbox requires each phone to join first.
- Partner portals use per-business demo passcodes (derived from `PARTNER_PASSCODE_SECRET`), not real auth.
- Anyone with a booking ID can cancel it from the status page (no caller login); IDs are 4 digits.
- Restaurant seatings are independent per start time and one party uses one table (no table joining).
- Text-mode eval: 32/40 on first contact with the real data, 40/40 after fixing what those calls exposed, so 40/40 is not held-out accuracy; a fresh, unseen set of test calls is still to do.
- The real data has no blocked slots and no doctor on leave; those rules are tested on the fixture data and shown live by blocking a slot on the partner portal.
- With the current fast LLM (~1.5 s per step), voice replies will need fillers and streaming to approach the ~1 s first-audio target (Phase 4).
- Payments are test mode only.
- All businesses, doctors, ratings and bookings are fictional sample data.
