# Claude Code prompt — build the Vaani frontend

> For Karthik and Akshit (anyone can use it). Open a terminal, `cd ~/Desktop`, run `claude`, and paste everything below the line.
> If `~/Desktop/vaani` already exists (Pranav's repo), the frontend goes in `~/Desktop/vaani/frontend`. If not, create `~/Desktop/vaani/frontend` anyway so it drops straight into Pranav's repo at merge time.
> Optional: put `vaani-master-plan.html` on your Desktop so Claude Code can read it.

---

You are the lead frontend engineer for **Vaani**, a hackathon project. Build the complete web frontend in **`~/Desktop/vaani/frontend`** as one Next.js app. Work in phases and stop after each for review. The voice AI backend is being built in parallel by Pranav, so **everything must work first against mocks** and then switch to the real backend with one environment variable.

## 0. How you must work

- Start in plan mode: read this whole prompt, then show me your plan and the component tree before writing code.
- **Check current official docs before using any library API** (Next.js App Router, Supabase JS + Realtime, shadcn/ui, Framer Motion, React Three Fiber/drei, Pipecat client SDK, Recharts). Use Context7 or the web docs. Do not guess import paths.
- Strict TypeScript, no `any`. Small components. Server components where possible, client components only where needed (realtime, audio, 3D, animation).
- Never commit secrets. `.env.local` is git-ignored; keep `.env.example` current.
- If `~/Desktop/vaani/docs/` or `~/Desktop/vaani/data/` exist, read them first. They are the source of truth and override defaults here if they differ. If `~/Desktop/vaani-master-plan.html` exists, read it too.
- Two people may work in this app at once: use feature branches (`feat/public-sites`, `feat/partner-portal`, …), and keep shared code in `components/ui`, `lib/`, `types/`.
- At the end of each phase: run lint, typecheck and Playwright tests, update `frontend/README.md`, commit, and give a short summary.

## 1. What Vaani is (context for every design decision)

Vaani is **one phone number answered by one AI voice agent** that books **restaurant tables** and **hospital/doctor appointments** for callers speaking **Telugu, Hindi and Indian English**. Callers use any phone, with no app and no internet. When the AI books on a call, the booking appears **live** (within about 2 seconds) on the business's partner portal and public mini-site, and the caller gets a WhatsApp message linking to a booking status page.

- Hackathon: Homingo Hack Days · Track: LLM apps · Problem statement C2 "Voice is the interface". Judges score: works live on a real problem, measured evidence, ambition, company potential, plus UX, latency and cost.
- Demo data: 2 Hyderabad areas (default Jubilee Hills and Gachibowli), 5 restaurants + 5 hospitals per area = 20 **fictional** businesses, all labelled sample data.
- **The frontend is how judges see that the AI "got the thing done".** In the demo, a TV shows a partner portal, a laptop shows the Live Call Studio, and a phone shows the WhatsApp card. They must all update together, instantly and beautifully.
- Team: Karthik suggested start = public side (landing, explore, mini-sites, status, payment). Akshit suggested start = partner portals, Live Call Studio, call logs, eval page. Anyone can take anything.

## 2. Stack

| Concern | Choice |
|---|---|
| Framework | Next.js (App Router) + TypeScript, `src/` layout |
| Styling | Tailwind CSS + CSS variables for design tokens |
| Components | shadcn/ui (Radix), Lucide icons |
| Motion | Framer Motion |
| 3D | React Three Fiber + drei for the voice orb (custom shader) |
| Charts | Recharts |
| State | Zustand (call/studio state), TanStack Query (server data) |
| Data | Supabase JS (reads with anon key under RLS) + Supabase Realtime |
| Writes | Only through the FastAPI backend (`NEXT_PUBLIC_BACKEND_URL`) — never write to Supabase from the browser |
| Browser call | Pipecat client SDK (WebRTC) to `POST {BACKEND}/webrtc/offer` |
| i18n | Lightweight dictionary for te / hi / en on public pages and status page |
| Tests | Playwright smoke tests per route, Vitest for utils |
| Hosting | Vercel |

## 3. Mock-first architecture (critical)

The frontend must run fully **without the backend or Supabase** for development and as a demo backup.

- `NEXT_PUBLIC_DATA_MODE=mock | live`.
- `src/lib/data/` exposes one interface (`getBusinesses`, `getRestaurant`, `getRestaurantSlots`, `getHospital`, `getDoctorSlots`, `getBooking`, `getPartnerBookings`, `patchBooking`, `blockSlot`, `setDoctorLeave`, `simulateBooking`, `getCalls`, `getCall`, `getEval`) with two implementations: `mock` and `live`.
- `src/lib/realtime/` exposes one subscribe interface (`subscribeBookings(businessId, date)`, `subscribeSlots(...)`, `subscribePayments(bookingId)`, `subscribeCallEvents(callId?)`) with `mock` (an in-memory event bus) and `live` (Supabase Realtime) implementations.
- **Mock data**: if `~/Desktop/vaani/data/*.json` exists, import from there. Otherwise create fixtures in `src/mocks/data/` in **exactly** the schema below (fictional names, `is_sample_data: true`, no real brands, doctors, phone numbers or addresses). Convert `day_offset` (0–6) to real dates relative to today at load time.
- **Mock call replay**: `src/mocks/calls/` holds 2 scripted calls (Hindi restaurant booking, Telugu hospital booking) as timed event sequences. A "Replay demo call" control in the Studio plays them through the mock event bus, so transcript, slots, timeline, portal flash and mini-site slot change all animate exactly as in a real call. Also a "Rush hour" replay that runs 4 calls in parallel.
- **Simulate booking**: a dev-only button (when `NEXT_PUBLIC_DEV_SIMULATE=true`) on portals and mini-sites that creates a booking through the data layer (mock bus or `POST /api/dev/simulate-booking`).

## 4. Contracts (must match the backend exactly — put these types in `src/types/`)

**Entities:** `Area {area_id, name_en, name_te, name_hi, aliases[], lat, lng, nearby_unsupported_areas[]}` · `Restaurant {restaurant_id, slug, name, name_spoken_te, name_spoken_hi, name_aliases[], area_id, address, cuisines[], food_type: 'veg'|'non-veg'|'both', rating, price_for_two_inr, highlight, popular_dishes[], opening_hours, features {parking, outdoor_seating, kids_friendly, wheelchair_access, live_music}, booking_rules {max_party_size, deposit_required_for_party_size_at_least, deposit_inr, cancellation}, tables[{table_id, capacity}], slot_length_minutes, faqs[{q, a_en, a_te, a_hi}], accent_color?, is_sample_data}` · `RestaurantSlot {restaurant_id, date, time, booked_table_ids[], blocked}` · `Hospital {hospital_id, slug, name, spoken names, aliases[], area_id, type, address, rating, highlight, specialities[], facilities {emergency_24x7, pharmacy, lab, ambulance, cashless_insurance, wheelchair_access}, opd_hours, languages_spoken[], faqs[], accent_color?, is_sample_data}` · `Doctor {doctor_id, hospital_id, name, gender, speciality, qualification, experience_years, languages[], consultation_fee_inr, schedule, slot_length_minutes, on_leave_dates[]}` · `DoctorSlot {doctor_id, date, time, status: 'free'|'booked'|'blocked'}` · `Booking {booking_id ('VN-xxxx'), service: 'restaurant'|'hospital', business_id, doctor_id?, date, time, party_size?, table_id?, name, phone, language, source: 'vaani_call'|'web'|'walk_in', status: 'confirmed'|'pending_payment'|'paid'|'arrived'|'checked_in'|'cancelled', call_id?, created_at}` · `Payment {payment_id, booking_id, amount_inr, provider, provider_ref, status}` · `Call {call_id, channel: 'phone'|'web', direction, from_number, started_at, ended_at, language, services_used[], transcript[{speaker, text, lang, ts}], outcome_json, tool_timeline[{ts, tool, summary}], latency_json, recording_url?, summary}`.

**Realtime events** (`call_events.type`): `call_started` · `language_detected` · `agent_switched` · `slot_filled` · `tool_called` · `booking_created` · `payment_updated` · `call_ended`. Example:
```json
{"call_id":"c_123","ts":"2026-11-23T20:12:05+05:30","type":"tool_called","payload":{"tool":"search_restaurants","summary":"Searched restaurants → 3 matches in Jubilee Hills (6 people, tomorrow)"}}
```
Also expect transcript events as `{"type":"transcript","payload":{"speaker":"caller"|"ai","text":"…","lang":"hi","final":true}}` and latency as `{"type":"latency","payload":{"stt":…,"llm_first_token":…,"tts_first_audio":…,"turn_total":…}}`. If the backend uses different names, adapt in one mapping file only.

**Backend endpoints used by the frontend:** `GET /api/businesses?area=&type=` · `GET /api/restaurants/{id}/slots?date=` · `GET /api/doctors/{id}/slots?date=` · `GET /api/bookings/{id}` · `GET /api/partners/{id}/bookings?date=` · `PATCH /api/bookings/{id}` · `POST /api/slots/block` · `POST /api/doctors/{id}/leave` · `POST /api/dev/simulate-booking` · `POST /webrtc/offer`.

**Env (`.env.example`):** `NEXT_PUBLIC_DATA_MODE=mock` · `NEXT_PUBLIC_BACKEND_URL=` · `NEXT_PUBLIC_SUPABASE_URL=` · `NEXT_PUBLIC_SUPABASE_ANON_KEY=` · `NEXT_PUBLIC_VAANI_PHONE=` · `NEXT_PUBLIC_DEV_SIMULATE=true` · `PARTNER_PASSCODES=` (JSON map slug → passcode, server-side only).

## 5. Design direction — make it unforgettable, not generic

The brief is "crazy frontend", but every screen must show real data, never decoration for its own sake. Avoid the usual AI-generated look: no purple-to-blue gradients, no glowing blobs, no gradient text, no emoji labels, no "New ✨" badges, no uppercase tracked micro-labels everywhere, no random glassmorphism.

- **Identity: "Hyderabad at night, warm and confident."** Deep ink background (near-black with a hint of blue), warm marigold/saffron as the single accent, soft cream text, a second cool accent (teal) only for "live" states. Light theme for public mini-sites (people open them from WhatsApp in daylight); dark theme for Studio and TV mode.
- **Typography that respects Indian scripts:** Anek Latin + Anek Telugu + Anek Devanagari (Google Fonts) for headings, so English, Telugu and Hindi look like one family; Inter or Noto Sans for body; a monospace for IDs and latency numbers. Every page must render Telugu and Devanagari correctly.
- **Motion with meaning:** slot counts tick down, booking cards slide in, a table pulses when booked, the orb breathes while listening. Respect `prefers-reduced-motion`.
- **Signature element — the voice orb:** an R3F sphere with a noise-displacement shader driven by audio amplitude (Web Audio `AnalyserNode` on the call's audio). States: idle (slow breathing), listening (teal ripples follow caller volume), thinking (slow marigold swirl), speaking (marigold pulses with TTS volume). Fallback to a 2D canvas or CSS version when WebGL is unavailable.
- **Per-business identity:** each fictional business gets an accent colour and a monogram logo generated from its name (no real logos or photos). Hero images: licence-free or generated food/clinic imagery, credited in `ATTRIBUTIONS.md`.
- **Sound:** the new-booking chime is generated with Web Audio (two soft tones), no copyrighted audio file.
- Accessibility: WCAG AA contrast, keyboard navigation, focus states, `aria-live="polite"` on transcripts and booking flashes, alt text, tap targets ≥ 44 px.

## 6. Pages (build all of them)

| Route | Suggested start | Purpose |
|---|---|---|
| `/` | Karthik | Landing |
| `/explore` | Karthik | Directory of 20 businesses |
| `/r/[slug]` | Karthik | Restaurant mini-site |
| `/h/[slug]` | Karthik | Hospital mini-site |
| `/b/[booking_id]` | Karthik | Booking status page |
| `/pay/[booking_id]` | Karthik | Mock test-mode payment page |
| `/partner/login` | Akshit | Partner login |
| `/partner/r/[slug]` | Akshit | Restaurant partner portal (TV) |
| `/partner/h/[slug]` | Akshit | Hospital partner portal |
| `/studio` | Akshit | Live Call Studio |
| `/calls`, `/calls/[id]` | Akshit | Call logs |
| `/eval` | Akshit | Evaluation page |

### 6.1 Landing `/`
- Full-height hero: the voice orb, headline "One number. Any service. Your language." (also shown in Telugu and Hindi), the phone number in large type, a **Talk to Vaani** button that starts a browser call (Pipecat client → `/webrtc/offer`; in mock mode, plays the replay call).
- When a browser call is active: the orb reacts, a compact live transcript appears under it, and an "End call" button.
- "Traditional vs Vaani" strip: 6 problems (language barriers, limited digital literacy, complicated apps, can't type, accessibility, poor customer service) each with the old way vs the Vaani way.
- Two service cards (Restaurants, Hospitals) linking to `/explore?type=…`.
- "Works on any phone, even without internet" band; languages strip (te, hi, en-IN; ta, kn, ml "coming").
- Footer: sample-data notice, team, GitHub link.

### 6.2 Explore `/explore`
- Filters: area (2 areas), service (restaurant / hospital), cuisine or speciality, veg only. Cards with monogram, name, rating badge "sample", highlight, next free slot. Links to mini-sites. A map-like area switcher (two area tiles), no external map tiles required.

### 6.3 Restaurant mini-site `/r/[slug]` (light theme, mobile-first)
- Header: monogram, name, area, cuisine tags, veg/non-veg tag, price for two, rating badge marked "sample".
- Hero image, highlight line, 3–5 popular dishes, feature icons (parking, outdoor seating, kids friendly, wheelchair access, live music).
- Opening hours, fictional address, a stylised area pin (no real map needed).
- FAQs accordion (language toggle te/hi/en).
- CTAs: "Book by calling Vaani" (tel: link) and "Talk to Vaani in browser".
- **Live availability widget (most important):** day picker (today + 6 days); lunch and dinner time chips; green chip shows free-table count, grey chip "Full", striped chip "Blocked". On a realtime booking for this restaurant, the count animates down, the chip briefly glows marigold, and a toast says "A table was just booked via Vaani". Fully booked chips flip to "Full".
- Footer banner: "Sample data for a hackathon demo".

### 6.4 Hospital mini-site `/h/[slug]` (light theme)
- Header with monogram, type, area, rating badge (sample), speciality chips, facility icons.
- Persistent red banner: "Emergency? Call 108 or 112 now".
- Doctor cards: initials avatar, name, qualification, experience, languages, consultation fee, weekly schedule, "on leave today" state.
- Per-doctor slot widget: day picker + 15-minute chips; booked slots grey out live with the same animation and toast.
- OPD hours, address, FAQs, Call Vaani buttons, sample-data banner.

### 6.5 Booking status `/b/[booking_id]` (light, mobile-first)
- Booking card: business, date, time, party size or doctor + speciality, name, booking ID (monospace), language.
- Live status timeline: booked → payment pending → paid (and arrived / checked in / cancelled), updating via realtime.
- Buttons: Pay now (if a deposit or fee applies), Add to calendar (.ics download), Directions (placeholder), Cancel booking (calls `PATCH`, with confirmation dialog).
- Language toggle te / hi / en. "Sample booking for a hackathon demo" note.

### 6.6 Mock pay `/pay/[booking_id]`
- Clearly labelled **TEST MODE**. Amount, booking summary, a "Pay (test)" button that marks the payment paid through the data layer and redirects to the status page. Never collect real card details.

### 6.7 Partner login `/partner/login`
- Pick a business from the 20, enter its demo passcode (checked server-side via a route handler against `PARTNER_PASSCODES`), set an httpOnly cookie, redirect to its portal. Note in the UI that this is a demo passcode, not real auth.

### 6.8 Restaurant partner portal `/partner/r/[slug]` (dark, desktop + TV)
- Top bar: monogram + name, date picker, **Live** dot (teal when realtime connected, grey when not), **Enable sound** button (browsers block audio until one click; make the button obvious until clicked).
- KPI strip: today's bookings, total covers, tables free now, next arrival (with countdown).
- **Floor plan:** table cards T1…Tn sized by capacity, laid out in a pleasing grid; colour = free / booked / arrived for the selected time slot; time-slot scrubber above it. Newly booked table pulses for 5 seconds.
- **Timeline view** (tab): rows = tables, columns = time slots 12:30–21:30, booked blocks show guest name + party size; current time line.
- **Bookings list:** time, name, party, table, source badge ("Vaani call · Hindi"), payment status, booking ID; filters; click opens a drawer with booking details and a link to the call transcript (`/calls/[id]`).
- **New booking flash:** a large card slides in from the right with the chime: "New booking · Pranav · 6 people · 8:30 PM · T4 · via Vaani (Hindi call, 42 s)". Stays 8 seconds, then joins the list.
- Staff actions: mark arrived, cancel, **block a slot** (time chip menu), close for the day. All through the data layer.
- **TV mode** (`?tv=1`): no navigation, huge type, floor plan + flash only, auto-follows the current or next dinner slot, cursor hidden after 3 seconds, wake lock if supported.

### 6.9 Hospital partner portal `/partner/h/[slug]`
- Same top bar, Live dot, Enable sound.
- KPI strip: appointments today per department, fees collected, next patient.
- **Doctor calendar:** one column per doctor (name, speciality), rows = 15-minute slots across OPD hours; booked slots show patient name and payment status chip; blocked and leave states shown clearly.
- Appointment list: booked → fee pending → paid → checked in; drawer with details + transcript link.
- Flash + chime on new appointments. Actions: check in, cancel, block a doctor slot, mark a doctor on leave today. TV mode.

### 6.10 Live Call Studio `/studio` (dark) — the demo centrepiece
- Layout: left = big voice orb + call status (ringing / talking / ended, duration, channel phone/web, caller's masked number); centre = **live transcript** (speaker bubbles, language tag TE/HI/EN on each line, partial text in a lighter shade until final); right = **slots panel** (area, business, date, time, party size / speciality / doctor, name — each ticks to ✓ with a small animation when filled) and **active agent badge** (Router → Restaurant / Hospital, with a transition when it switches).
- Bottom: **agent activity timeline** — each `tool_called` event as a row: time, icon, plain-language summary (e.g. "Checked Dumgalli Courtyard slots → 19:00 free (20:30 full)"); `booking_created` row highlighted with the booking ID and a link to the portal.
- **Latency meter:** per turn, stacked bar (STT / LLM / TTS) with the total, plus running median; colour turns warning above 1.5 s.
- **Multi-call grid** (toggle): one tile per live call (status, language, service, last line of transcript, latency); tiles turn green when a booking is made. Used for the "rush hour" demo (4 calls).
- Controls: Talk to Vaani (browser call), Replay demo call (Hindi restaurant / Telugu hospital), Rush hour replay (mock), pin a call.

### 6.11 Call logs `/calls`, `/calls/[id]`
- List: time, channel, language, service, outcome (booked / alternatives offered / unsupported area / emergency redirect / no booking), duration, median latency. Filters.
- Detail: full transcript with language tags, outcome JSON (pretty, collapsible), tool timeline, latency chart per turn, recording player if `recording_url`, summary.

### 6.12 Evaluation `/eval`
- Reads `GET` eval results (or a JSON file in mock mode with clearly fake placeholder numbers labelled "placeholder until eval runs").
- Charts (Recharts): booking accuracy by language (bars), latency distribution (median/slowest per channel), load test (median reply time vs concurrent callers 1/4/10/15), naturalness rating, cost per call minute. A table of the 40 test calls with pass/fail and the reason.
- Short "How we measured" notes under each chart.

## 7. Shared building blocks

- `components/ui` (shadcn), `components/brand` (Logo, Monogram, RatingBadge "sample", SampleDataBanner, LanguageTag, SourceBadge), `components/booking` (SlotChip, DayPicker, AvailabilityWidget, DoctorSlotGrid, BookingCard, StatusTimeline, BookingFlash), `components/call` (VoiceOrb, Transcript, SlotsPanel, AgentBadge, ActivityTimeline, LatencyMeter, CallTile), `components/partner` (FloorPlan, TableCard, TimelineView, DoctorCalendar, KpiStrip, LiveDot, EnableSoundButton).
- Hooks: `useBookings`, `useSlots`, `useDoctorSlots`, `useBooking`, `useCallEvents`, `useActiveCalls`, `useChime`, `useTvMode`, `useBrowserCall`, `useAudioLevel`.
- Utilities: date helpers in IST (`Asia/Kolkata`), spoken-friendly time formatting, booking ID formatter, masked phone (`+91 ••••• 4210`), `.ics` generator.
- i18n: `src/i18n/{en,te,hi}.ts` for public page strings; have a native speaker review Telugu and Hindi before the demo.

## 8. Quality bar

- Lighthouse ≥ 90 for performance and accessibility on mini-sites and status page (mobile).
- No layout shift when realtime updates land; animations under 400 ms.
- Works on iPhone Safari and Android Chrome (mini-sites, status page), desktop Chrome (portals, studio), and a 1080p TV browser (TV mode).
- Graceful states everywhere: loading skeletons, empty states, realtime disconnected banner with auto-reconnect, unknown slug 404, booking not found.
- Playwright: one smoke test per route + one end-to-end mock test: "simulate a booking → portal flash appears, mini-site chip count drops, status page shows confirmed".

## 9. Phases (stop after each for review)

1. **Foundation:** Next.js app, Tailwind tokens (dark + light), fonts (Anek Latin/Telugu/Devanagari + body), shadcn/ui, types from section 4, data and realtime layers with mock implementations, mock fixtures (or import `~/Desktop/vaani/data`), mock event bus, i18n scaffold, layout shells, `.env.example`, README.
2. **Public side:** landing (orb in 2D first, R3F after), explore, restaurant + hospital mini-sites with live availability widgets, status page, mock pay page.
3. **Partner side:** login, restaurant portal (floor plan, timeline, list, flash + chime, actions, TV mode), hospital portal (doctor calendar, list, flash, actions, TV mode).
4. **Studio and logs:** Live Call Studio with replay calls and rush-hour replay, multi-call grid, call logs list + detail, eval page.
5. **3D orb + polish:** R3F shader orb with audio-reactive states and fallbacks, motion polish, accessibility pass, Lighthouse pass, Playwright suite.
6. **Live mode:** live implementations of the data and realtime layers (Supabase + backend endpoints), Pipecat browser call on `/` and `/studio`, switch with `NEXT_PUBLIC_DATA_MODE=live`, test against Pranav's backend, Vercel deploy config.

## 10. Deliverables for the hackathon submission

- Screenshots of every page (light/dark, mobile/desktop, TV mode) saved to `frontend/docs/screenshots/` for the README.
- A 20–30 s screen recording of the mock replay showing studio + portal + mini-site updating together (backup for the demo video).
- `ATTRIBUTIONS.md` entries for fonts, icons, images and libraries.
- Notes for `AI_USAGE.md`: how AI tools helped build the frontend and that a human reviewed the code.
- `frontend/README.md`: how to run in mock mode (`npm i && npm run dev`), how to switch to live mode, env vars, routes, and the demo checklist (open TV portal with `?tv=1`, click Enable sound, open Studio, keep the replay ready as backup).

Start now: show me your plan for Phase 1, then build it.
