# Data prompt (ChatGPT)

**Owner:** Rithvik (suggested) — anyone can run it.

How to use:

1. Replace `[AREA_1]` / `[AREA_2]` below with the confirmed areas (default **Jubilee Hills** and **Gachibowli**; ID prefixes `jh` and `gb`). If you pick other areas, change the `area_id`s and the ID prefixes consistently.
2. Paste everything inside the box into a new ChatGPT chat. Generate the files one at a time, typing `next` after each.
3. Save each block as the matching file in `data/` (overwrite the placeholder).
4. Run `uv run python scripts/validate_data.py`. Fix anything it reports (ask ChatGPT to regenerate that file with the error message), then `uv run python scripts/seed.py`.
5. Ask a native Telugu speaker and a native Hindi speaker to read the names, phrases and agent lines.

The schema below is the contract in `docs/CONTRACTS.md` §7. Don't change field names.

---

```text
You are helping me create FICTIONAL demo data for a hackathon project. Read the whole brief before generating anything.

=== PROJECT CONTEXT ===
Project: "Vaani" — an AI voice assistant that answers real phone calls in Telugu, Hindi and Indian English (code-mixed speech is normal). One phone number handles two services:
1. Restaurant table booking
2. Hospital/doctor appointment booking
Callers ask things like "Jubilee Hills lo manchi restaurant cheppu, repu night ki 6 mandi" or "Gachibowli mein dermatologist chahiye Saturday ko". The AI searches our database, suggests the top 3 options with ratings, reads available time slots, books, and sends a WhatsApp confirmation.
This data powers: (a) the AI's search and booking tools, (b) a small public website per business, (c) a partner portal per business, (d) our evaluation test set.

=== HARD RULES ===
- ALL businesses, doctors and people must be FICTIONAL. Do NOT use real restaurant names, real hospital names, real chains, real brands, or real doctors. Invent original names that sound natural for Hyderabad.
- Do NOT include real phone numbers, real emails or real street addresses. Phone placeholders only: "DEMO-R-001" … "DEMO-R-010" for restaurants, "DEMO-H-001" … "DEMO-H-010" for hospitals. No emails anywhere.
- Addresses: only "<fictional street/landmark name>, [AREA]". Invent the landmark names.
- Every record must include "is_sample_data": true.
- Ratings are our own sample ratings (no reviews, no reviewer names). Give one short neutral "highlight" line instead of reviews.
- Doctors: generic qualifications only (e.g. "MBBS, MD (Dermatology)"). Mix of genders. No medical advice anywhere, including FAQs.
- Areas: ONLY two areas exist in this demo: [AREA_1] and [AREA_2] (Hyderabad).
- Output STRICT valid JSON only, one code block per file, exactly matching the schemas below. No comments, no trailing commas, no "..." left in the output.
- Time slots use "day_offset" (0 = today, 1 = tomorrow ... 6) instead of real dates.
- Times in 24h "HH:MM".
- Telugu fields in Telugu script, Hindi fields in Devanagari, unless the field says "romanised".

=== FILE 1: areas.json ===
A JSON array with one object per area:
{"area_id": "jubilee_hills", "name_en": "Jubilee Hills", "name_te": "<Telugu script>", "name_hi": "<Devanagari>", "aliases": ["jubilee hills", "jubili hills", "jh", "<common mis-hearings, transliterations, all lower-case>"], "lat": 17.43, "lng": 78.41, "nearby_unsupported_areas": ["<4-6 real neighbouring area names>"], "unsupported_area_reply": {"te": "...", "hi": "...", "en": "..."}, "is_sample_data": true}
- 6-10 aliases per area.
- unsupported_area_reply: polite, natural, romanised code-mixed for te and hi (how people actually speak), meaning "Sorry, for this demo we only have restaurants/hospitals in [AREA_1] and [AREA_2]. Shall I check one of these?"

=== FILE 2: restaurants.json ===
A JSON array. Exactly 5 restaurants in [AREA_1] (ids r_jh_01..r_jh_05) and 5 in [AREA_2] (r_gb_01..r_gb_05). Varied cuisines (Hyderabadi biryani, South Indian, North Indian, Indo-Chinese, cafe, seafood, pure veg, multi-cuisine), price ranges, ratings 3.8-4.8 (no two identical in the same area), veg/non-veg.
{"restaurant_id": "r_jh_01", "slug": "<name-in-kebab-case>-jubilee-hills", "name": "<fictional>", "name_spoken_te": "<Telugu script>", "name_spoken_hi": "<Devanagari>", "name_aliases": ["<short forms / mis-hearings, lower-case>"], "area_id": "jubilee_hills", "address": "<fictional landmark>, Jubilee Hills", "cuisines": ["North Indian"], "food_type": "veg | non-veg | both", "rating": 4.5, "price_for_two_inr": 1200, "highlight": "<one neutral line>", "popular_dishes": ["<3-5>"], "opening_hours": {"mon": ["12:00-15:30", "19:00-23:00"], "tue": [...], "wed": [...], "thu": [...], "fri": [...], "sat": [...], "sun": [...]}, "features": {"parking": true, "outdoor_seating": false, "kids_friendly": true, "wheelchair_access": true, "live_music": false}, "booking_rules": {"max_party_size": 12, "deposit_required_for_party_size_at_least": 8, "deposit_inr": 500, "cancellation": "<short rule>"}, "tables": [{"table_id": "T1", "capacity": 2}, ...], "slot_length_minutes": 90, "accent_color": "#RRGGBB", "faqs": [{"q": "...", "a_en": "...", "a_te": "...", "a_hi": "..."}], "phone": "DEMO-R-001", "is_sample_data": true}
- food_type is exactly one of "veg", "non-veg", "both".
- opening_hours: all 7 day keys, open every day (day_offset maps to a different weekday depending on when we load the data, so no closed days). Weekend hours may be longer. Every restaurant must cover dinner (19:00-21:30 starts); most also cover lunch (12:30-14:00 starts).
- tables: 8-12 tables, capacities 2/4/6/8/10/12, table_ids T1, T2, ... in order. One party sits at one table.
- max_party_size between 6 and 12 and NOT bigger than the largest table's capacity; deposit threshold between 6 and 10 and not above max_party_size.
- 4-5 FAQs per restaurant (parking, veg options, kids, timings, deposit, etc.). a_te / a_hi romanised code-mixed.

=== FILE 3: restaurant_availability.json ===
A JSON array. Bookable start times are fixed: lunch 12:30, 13:00, 13:30, 14:00 and dinner 19:00, 19:30, 20:00, 20:30, 21:00, 21:30 (only inside that restaurant's opening hours).
List ONLY the slots that already have bookings or are blocked; every slot not listed is fully free.
{"restaurant_id": "r_jh_01", "day_offset": 1, "time": "20:00", "booked_table_ids": ["T1", "T3"], "blocked": false}
- Weekends and 20:00-21:00 busier.
- At least 2 slots per restaurant FULLY booked (every table_id of that restaurant listed).
- At least 1 restaurant per area almost full tomorrow night (day_offset 1).
- r_jh_01 must have 20:00 on day_offset 1 fully booked, with 19:30 and 20:30 still having a table for 6 (this is our demo call).
- 2-3 slots in total with "blocked": true and booked_table_ids [] (staff blocked).
- 80-140 rows in total.

=== FILE 4: hospitals.json ===
A JSON array. Exactly 5 hospitals/clinics in [AREA_1] (h_jh_01..h_jh_05) and 5 in [AREA_2] (h_gb_01..h_gb_05). Mix of multi-speciality hospitals and clinics; ratings 3.8-4.8, varied.
{"hospital_id": "h_gb_01", "slug": "<name-in-kebab-case>-gachibowli", "name": "<fictional>", "name_spoken_te": "...", "name_spoken_hi": "...", "name_aliases": ["..."], "area_id": "gachibowli", "type": "multi-speciality hospital | clinic", "address": "<fictional landmark>, Gachibowli", "rating": 4.4, "highlight": "<one neutral line>", "specialities": ["subset of: General Medicine, Dermatology, Gynecology, Pediatrics, Orthopedics, ENT, Cardiology, Dental, Ophthalmology"], "facilities": {"emergency_24x7": true, "pharmacy": true, "lab": true, "ambulance": true, "cashless_insurance": true, "wheelchair_access": true}, "opd_hours": {"mon": "09:00-20:00", "tue": "...", "wed": "...", "thu": "...", "fri": "...", "sat": "...", "sun": "09:00-14:00"}, "languages_spoken": ["Telugu", "Hindi", "English"], "accent_color": "#RRGGBB", "faqs": [{"q": "...", "a_en": "...", "a_te": "...", "a_hi": "..."}], "phone": "DEMO-H-001", "is_sample_data": true}
- type is exactly "multi-speciality hospital" or "clinic". Clinics have 2-4 specialities; hospitals 5-9.
- Every speciality must be offered by at least one hospital in EACH area.
- 4-5 FAQs each (parking, insurance, reports, timings, walk-ins). No medical advice.

=== FILE 5: doctors.json ===
A JSON array. 1-3 doctors per speciality each hospital offers (clinics fewer). Fictional names, mixed genders. doctor_id = "d_<area>_<nn>_<spec>_<k>" with spec codes: genmed, derm, gyn, peds, ortho, ent, cardio, dental, ophth.
{"doctor_id": "d_gb_01_derm_1", "hospital_id": "h_gb_01", "name": "Dr. <fictional>", "name_spoken_te": "...", "name_spoken_hi": "...", "gender": "female | male", "speciality": "Dermatology", "qualification": "MBBS, MD (Dermatology)", "experience_years": 9, "languages": ["Telugu", "English"], "consultation_fee_inr": 600, "schedule": {"mon": "10:00-13:00", "wed": "16:00-19:00", "sat": "10:00-14:00"}, "slot_length_minutes": 15, "on_leave_day_offsets": [], "is_sample_data": true}
- schedule: only days the doctor works, one "HH:MM-HH:MM" range per day, inside the hospital's OPD hours, on the 15-minute grid. At least one doctor per speciality per area works all 7 days with the same hours (these are the ones we use in test calls and FILE 6).
- hospitals' opd_hours must therefore be open all 7 days (Sunday may be shorter but must contain those doctors' hours).
- consultation_fee_inr 300-1500.
- Exactly one doctor has on_leave_day_offsets [2]; all others [].

=== FILE 6: doctor_availability.json ===
A JSON array. List ONLY doctor-days that already have bookings or blocked slots; everything else in the schedule is free.
{"doctor_id": "d_gb_01_derm_1", "day_offset": 1, "booked_times": ["10:00", "10:15", "11:30"], "blocked_times": []}
- day_offset maps to a different weekday depending on when we load the data. So every doctor that appears in this file or in test_calls.json must work ALL 7 days (hours may differ by weekday, but every booked/blocked time must be a slot on every weekday) (set that in FILE 5), and every time must be a slot start inside those hours. Mornings busier.
- At least one doctor FULLY booked tomorrow (every slot of the schedule listed).
- 1-2 blocked_times entries in total.

=== FILE 7: speciality_mapping.json ===
One JSON object:
{"phrases": [{"phrase": "skin doctor", "lang": "en", "speciality": "Dermatology"}, ...],
 "emergency_phrases": [{"phrase": "chest pain", "lang": "en"}, ...],
 "emergency_reply": {"te": "...", "hi": "...", "en": "Please call 108 or 112 immediately. I can't book for emergencies."}}
- At least 60 everyday phrases covering every speciality, in English, Telugu (script AND romanised) and Hindi (script AND romanised), e.g. "skin doctor", "pillala doctor", "aankh ka doctor", "pallu noppi", "periods problem", "knee pain", "chevi noppi", "fever". lang is "en", "te" or "hi".
- At least 30 emergency phrases (te/hi/en): chest pain, can't breathe, heavy bleeding, unconscious, accident, stroke signs, poisoning, seizures, suicidal thoughts, etc.
- emergency_reply: the exact line the AI says (tells the caller to call 108 or 112 immediately; no booking), te and hi romanised code-mixed.

=== FILE 8: test_calls.json (evaluation set) ===
A JSON array of 40 caller scripts: T01-T20 restaurant, T21-T40 hospital. About 40% te-en (16), 35% hi-en (14), 25% en-IN (10), spread across both services.
{"test_id": "T01", "service": "restaurant | hospital", "language_mix": "te-en | hi-en | en-IN", "scenario": "happy_path | unsupported_area | slot_full | mid_call_change | vague_request | party_limit | deposit_needed | doctor_fully_booked | doctor_on_leave | emergency | faq", "caller_turns": ["<caller lines, natural spoken style, romanised>"], "expected": {"intent": "book | info | unsupported_area | emergency", "area_id": "jubilee_hills or null", "business_id": "r_jh_01 or null", "speciality": "Dermatology or null", "doctor_id": "... or null", "day_offset": 1, "time": "20:30", "party_size": 6, "outcome": "booked | offered_alternatives | declined_unsupported_area | redirected_emergency | answered_faq | no_availability"}}
- Every scenario appears at least twice. Use null (not "") for fields that don't apply.
- caller_turns: 3-6 lines a real caller would say, including the name and "yes" to confirm when booking.
- expected must be consistent with FILES 2-6 (e.g. a slot_full test asks for a slot that file 3 lists as fully booked; "time" is the time finally booked).

=== FILE 9: agent_phrases.json ===
A JSON array. Natural, warm, casual lines (how people in Hyderabad really speak, NOT textbook language), te-en, hi-en and en-IN versions, exactly 3 variations each, 1-2 short sentences, with {placeholders} like {business}, {time}, {date}, {party_size}, {name}, {booking_id}, {area_1}, {area_2}, {options}:
greeting_with_ai_disclosure, ask_area, ask_date_time, ask_party_size, ask_name, reading_top3_intro, slot_full_offer_alternatives, confirm_booking_readback, booking_done_whatsapp_sent, filler_checking, didnt_catch_that, silence_check, anything_else, goodbye, unsupported_area, emergency_redirect, transfer_to_human, never_ask_otp.
{"key": "slot_full_offer_alternatives", "te-en": ["...", "...", "..."], "hi-en": ["...", "...", "..."], "en-IN": ["...", "...", "..."]}
- Every greeting_with_ai_disclosure line must say the caller is talking to Vaani, an AI assistant.
- en-IN means Indian English phrasing (no British/US idioms).

=== FINAL CHECK (before answering each file) ===
- Every restaurant_id / hospital_id / doctor_id referenced anywhere exists.
- Every booked table_id exists in that restaurant; every booked or blocked doctor time is inside that doctor's schedule for that weekday.
- Exactly 5 restaurants and 5 hospitals per area.
- No real brand, hospital, doctor, phone number or address.
- "is_sample_data": true on every record.
- All JSON is valid (no comments, no trailing commas, no placeholders like "...").

Generate the files one at a time, starting with FILE 1. After each file, wait for me to type "next".
```
