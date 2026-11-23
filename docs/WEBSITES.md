# Vaani — Websites

All pages live in one Next.js (App Router, strict TypeScript) app in `frontend/`. They read Supabase with the anon key under read-only RLS and subscribe to Realtime; **every write goes through the FastAPI backend** so the websites and the AI follow the same rules.

Owners (suggested starts, anyone can help): Karthik = public side + payments; Akshit = partner + ops side.

**Building the frontend with Claude Code:** paste [FRONTEND_PROMPT.md](FRONTEND_PROMPT.md) (mock-first plan, design direction, components, phases). That prompt defers to `docs/`, so where it differs from the backend, follow *Frontend ↔ backend notes* below.

## Site map

| Route | Who sees it | Purpose | Start |
|---|---|---|---|
| `/` | Everyone | Landing: audio-reactive 3D voice orb, "One number. Any service. Your language.", "Talk to Vaani" browser call, phone number, 2 service cards, traditional-vs-voice-first strip, languages strip | Karthik |
| `/explore` | Everyone | Directory of the 20 sample businesses, filter by area and service | Karthik |
| `/r/[slug]` | Public | Restaurant mini-site | Karthik |
| `/h/[slug]` | Public | Hospital mini-site | Karthik |
| `/b/[booking_id]` | Caller (WhatsApp link) | Booking status page | Karthik |
| `/pay/[booking_id]` | Caller | Mock test-mode payment page (if no gateway hosted page) | Karthik |
| `/partner/login` | Staff | Pick business + per-business demo passcode | Akshit |
| `/partner/r/[slug]` | Restaurant staff | Restaurant partner portal (TV in the demo) | Akshit |
| `/partner/h/[slug]` | Hospital staff | Hospital partner portal | Akshit |
| `/studio` | Team, judges | Live Call Studio | Akshit |
| `/calls`, `/calls/[id]` | Team | Call logs | Akshit |
| `/eval` | Judges | Evaluation numbers | Akshit |

## Shared foundation

- Next.js + TypeScript (strict) + Tailwind + shadcn/ui + Lucide; one Vaani design system with tokens for colour, type and spacing, **dark and light**.
- Supabase client + Realtime hooks: `useBookings(businessId, date)`, `useRestaurantSlots(id, date)`, `useDoctorSlots(id, date)`, `useCallEvents(callId?)`, `useRealtimeStatus()` (drives the green "Live" dot).
- Typed API client for `CONTRACTS.md` §3 endpoints.
- Per-business accent colour (`accent_color`) and a monogram logo generated from the fictional name.
- Dev-only **"Simulate a call booking"** button (shown when `DEV_SIMULATE=true`) → `POST /api/dev/simulate-booking`, which fires the same events as a real call.
- Footer banner on public pages: "Sample data for a hackathon demo".
- Mobile-first mini-sites (opened from WhatsApp); desktop + TV layouts for portals. Framer Motion for subtle motion only.
- Zustand for client state (studio call tiles, sound enabled, selected date).

## Page specs

### Landing `/`
Hero with the audio-reactive voice orb (React Three Fiber; reacts to mic/call audio levels, idles gently otherwise) and the line **"One number. Any service. Your language."** · "Talk to Vaani" button (Pipecat client, WebRTC → `POST /webrtc/offer`) · the phone number · two service cards (restaurants, hospitals) · "traditional vs voice-first" strip (IVR menus, apps, typing → just talk) · languages strip (te, hi, en-IN; ta/kn/ml "being tuned") · "works on any phone, no app, no internet".

### Restaurant mini-site `/r/[slug]`
- Header: name, area, cuisine tags, veg/non-veg tag, price for two, rating badge marked **"sample"**.
- Hero image: licence-free or generated food image — never a real restaurant photo or logo; credit in `ATTRIBUTIONS.md`.
- Highlight line, 3–5 popular dishes, feature icons (parking, outdoor, kids, wheelchair, live music).
- Hours, fictional address, map pin at the area centre, FAQs.
- "Book by calling Vaani" + "Talk to Vaani in browser" buttons.
- **Live availability widget:** day picker (today + 6), time chips green with free-table count / grey "Full"; the count animates down on a booking; toast **"A table was just booked via Vaani"**.
- Sample-data footer banner.

### Hospital mini-site `/h/[slug]`
- Header + speciality chips + facility icons; rating badge "sample".
- Red banner: **"Emergency? Call 108 or 112 now"**.
- Doctor cards: initials avatar, name, qualification, experience, languages, fee, weekly schedule.
- Per-doctor slot widget (day picker + 15-min chips); booked slots turn grey live.
- OPD hours, fictional address, FAQs, Call Vaani buttons.

### Booking status `/b/[booking_id]`
Booking card · live status timeline (booked → payment pending → paid; arrived/checked in) · Pay now · Add to calendar (`.ics`) · directions placeholder · Cancel (→ `PATCH /api/bookings/{id}`) · language toggle te / hi / en.

### Mock pay `/pay/[booking_id]`
Shows amount + "TEST MODE" badge and a "Pay (test)" button that calls the backend, which marks the payment paid through the same code path as the webhook.

### Partner login `/partner/login`
Pick business → enter its demo passcode (listed in README "Known limits"). Stores a session in the browser only.

### Restaurant partner portal `/partner/r/[slug]`
- Top bar: business name, date picker, green **Live** dot when Realtime is connected, **Enable sound** button (browsers block autoplay until one click).
- KPI strip: today's bookings, covers, tables free now, next arrival.
- Floor plan: table cards T1…Tn with capacity, coloured free / booked / arrived for the selected time; a new booking pulses.
- Timeline view: rows = tables, columns = time slots; booked blocks show name + party size.
- Bookings list: time, name, party, table, source ("Vaani call · Hindi"), payment status, booking ID.
- **New booking flash** card + chime: "New booking · Pranav · 6 people · 19:00 · T6 · via Vaani (Hindi call, 42 s)", link to the call transcript.
- Staff actions: mark arrived, cancel, block a slot (the AI must then treat it as full), close for the day.
- **TV mode** `?tv=1`: large type, no nav, dark, auto-follows the current dinner slot.

### Hospital partner portal `/partner/h/[slug]`
- Same top bar (Live dot, Enable sound).
- KPI strip: appointments per department, fees collected, next patient.
- Doctor calendar: a column per doctor, rows = 15-min slots; booked slots show patient + payment status.
- Appointment list: booked → fee pending → paid → checked in.
- Flash + chime on new appointments.
- Actions: check in, cancel, block a doctor slot, doctor on leave for a day.
- TV mode.

### Live Call Studio `/studio`
Orb reacting to call audio · live transcript with TE/HI/EN tags · slots filling live (area ✓ date ✓ time ✓ people ✓) · active agent badge (Router / Restaurant / Hospital) · agent activity timeline from `tool_called` events · latency meter per turn · grid of live call tiles for multiple calls (ringing / talking / done).

Example timeline:
```
11:42:03 Language: Hindi · Service: Restaurant
11:42:05 Searched restaurants → 3 matches in Jubilee Hills (6 people, tomorrow)
11:42:14 Checked Dumgalli Courtyard slots → 19:00 free (20:30 full)
11:42:26 Booked table T6 · 19:00 · ID VN-4821
11:42:27 WhatsApp confirmation sent · Dumgalli Courtyard notified
```

### Call logs `/calls`, `/calls/[id]`
List (time, channel, language, service, outcome, duration) + detail: transcript, outcome JSON, tool timeline, latency breakdown, recording link.

### Evaluation `/eval`
Accuracy by language, latency (median / slowest), naturalness, load-test table (1 / 4 / 10 / 15 callers), cost per minute — Recharts, reading the results files written by `backend/eval/`.

## WhatsApp message format

```
✅ Booking confirmed — Vaani
Dumgalli Courtyard, Jubilee Hills
Tue 24 Nov · 7:00 PM · 6 people · Table T6
Booking ID: VN-4821
Status & directions: <site>/b/VN-4821
(Sample booking for a hackathon demo)
```

Hospital variant replaces the table line with `Dr. <name> · <speciality>` and adds `Fee ₹600 · Pay (test): <link>`.

## Realtime subscriptions

`bookings`, `restaurant_slots`, `doctor_slots`, `payments`, `call_events`, filtered by business ID or call ID.

## Frontend ↔ backend notes

Where `FRONTEND_PROMPT.md` and the built backend (Phase 2, [CONTRACTS.md](CONTRACTS.md) §2–4) differ, the backend contract wins:

| Topic | FRONTEND_PROMPT.md says | Backend does |
|---|---|---|
| Partner passcodes | `PARTNER_PASSCODES` JSON map checked by a Next.js route handler | Per-business 6-digit codes derived from `PARTNER_PASSCODE_SECRET`; send `X-Partner-Passcode` on partner endpoints (`GET /api/partners/{id}/bookings`, `PATCH` arrived/checked_in, `POST /api/slots/block`, `POST /api/doctors/{id}/leave`). List: `uv run python scripts/partner_passcodes.py`. The login page can verify a code by calling the partner bookings endpoint |
| Booking phone | `Booking.phone` | Never sent to the browser: API returns `phone_masked` (`+91••••••3210`); Supabase anon reads of `bookings` can't select `phone`, and `calls` can't select `from_number` |
| Transcript speaker | `"caller" \| "ai"` | `"caller" \| "vaani"` (map in the one mapping file) |
| Mock pay | "marks the payment paid through the data layer" | Live mode: `POST /api/payments/{booking_id}/mock-pay` (when `PAYMENT_PROVIDER=mock`) |
| Slot endpoints | shapes not specified | `{restaurant_id, date, in_window, slots: [{time, free_tables, total_tables, blocked, past}]}` and `{doctor_id, date, on_leave, slots: [{time, status, past}]}` |
| Businesses | — | `GET /api/businesses` items carry `type` + `id`; hospitals include `doctors` |
| Simulate booking | `POST /api/dev/simulate-booking` | Same, body `{business_id, doctor_id?, date?, time?, party_size?, name?, language?}`; 404 unless `DEV_SIMULATE=true` |
| Errors | — | `{"detail": {"error": "<CODE>", "message"}}` |

## Acceptance test

1. A booking made on a call appears on the partner portal, the mini-site slot widget and the WhatsApp message **within 2 seconds**.
2. A slot blocked on the portal is **refused by the AI** on the next call.

Until calls work, run both with the Simulate-booking button.
