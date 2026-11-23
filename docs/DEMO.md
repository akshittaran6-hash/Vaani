# Vaani — Demo setup and video script

The demo proves "it got the thing done" by showing four things within about 2 seconds: the call, the AI's actions, the business receiving the booking, and the caller getting the confirmation.

## Screens

| Screen | Shows |
|---|---|
| TV | Partner portal in TV mode (`/partner/r/<slug>?tv=1`) for the business being booked; the new booking flashes with a chime |
| Laptop / projector | Live Call Studio (`/studio`): transcript with language tags, slots filling, agent activity timeline, latency meter |
| Caller's phone, mirrored (QuickTime for iPhone, scrcpy for Android) | The live call, then the WhatsApp confirmation card |
| Optional 4th panel | The restaurant's mini-site: the booked slot's count drops live |

## Before going live (checklist)

- [ ] Backend deployed (or local + ngrok) and `GET /health` OK; Twilio voice webhook points at `/twilio/inbound`
- [ ] Data reseeded today (`uv run python scripts/seed.py` — wipes test bookings too) so slots are on current dates and the demo slots are full (Dumgalli Courtyard tomorrow 19:30–21:30 for 6 people; Dr. Navisha Vaanavolu tomorrow; Pulao Pankthi tomorrow night for 3+)
- [ ] Click **Enable sound** on the TV portal
- [ ] All team phones (4 + 1 spare) verified on Twilio and joined to the WhatsApp sandbox
- [ ] Studio open and showing the green Live dot
- [ ] Backup video ready on the laptop
- [ ] Invite a judge to call and book while the TV shows the portal

## Demo scenarios (from the real data; checked by `backend/tests/test_real_data.py`)

| Scenario | What happens | Test call |
|---|---|---|
| Hindi restaurant, Jubilee Hills, tomorrow, 6 people | Top 3: Dumgalli Courtyard 4.7, Tandoor Taaraka 4.5, Aavakaaya Arugu 4.4. Caller asks Dumgalli at 8:30 → full (19:30–21:30 full for 6); Vaani offers Dumgalli 7:00 or Tandoor Taaraka 8:30 | T13 |
| Payment demo | Aavakaaya Arugu needs a ₹300 test deposit for 6+ people → WhatsApp pay link → `/pay/VN-…` | T09 (Tandoor, 8 people) |
| Telugu hospital, Gachibowli, skin doctor tomorrow | Vaana Grove 4.7: Dr. Navisha Vaanavolu fully booked → Dr. Suvin Rellimudi from 15:00 (fee ₹900); or Taarika Skin and Dental Clinic 4.5 (Dr. Vaanika Neelimodugu, morning) | T23 |
| Restaurant full for a group | Pulao Pankthi (Gachibowli, 4.8) has no dinner table tomorrow for 3+ people; one 2-seater is left (T16 books it) | T07 |
| Unsupported area / emergency | Kondapur, Madhapur, Manikonda, Shaikpet, Khajaguda → polite "only Jubilee Hills and Gachibowli"; "gundelo noppi, oopiri aadatledu" → 112 / 108, no booking | T04, T26 |

## Video script (~3 minutes, recorded with OBS)

| Time | Segment | What's on screen |
|---|---|---|
| 0:00–0:15 | **Hook:** "One number. Any service. Your language." | Landing page orb, phone dialling |
| 0:15–1:05 | **Hindi restaurant booking:** search → requested slot full → alternative offered → booked → TV flashes + chime → WhatsApp arrives | Phone mirror + Studio + TV |
| 1:05–1:55 | **Telugu hospital appointment:** "skin doctor" → Dermatology → doctor slots → booked → test-mode fee paid → status "Paid" everywhere | Phone + hospital portal + `/b/VN-xxxx` |
| 1:55–2:15 | **Unsupported area + emergency:** polite "only these two areas"; chest-pain phrase → "call 108 / 112", no booking | Studio timeline |
| 2:15–2:40 | **Rush hour:** 4 phones at once in different languages, 4 tiles turn green; load-test table at 1 / 4 / 10 / 15 | Studio tiles grid + `/eval` |
| 2:40–3:00 | **Evidence + vision:** accuracy, latency, naturalness, cost; any business joins as a partner, new services are new playbooks | `/eval`, closing slide |

## Agent activity timeline (what judges should see)

```
11:42:03 Language: Hindi · Service: Restaurant
11:42:05 Searched restaurants → 3 matches in Jubilee Hills (6 people, tomorrow)
11:42:14 Checked Dumgalli Courtyard slots → 19:00 free (20:30 full)
11:42:26 Booked table T6 · 19:00 · ID VN-4821
11:42:27 WhatsApp confirmation sent · Dumgalli Courtyard notified
```

## Fallbacks

| If… | Then |
|---|---|
| Twilio trial minutes run low | Use browser calls ("Talk to Vaani") for rehearsals; save phone minutes for the recording |
| WhatsApp sandbox session expired | Re-send the join code from each phone the day before; SMS fallback; status page link always works |
| Live call fails on stage | Play the backup video segment, then retry once |
