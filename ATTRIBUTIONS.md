# Attributions

Vaani is built on open-source libraries and third-party services. This file is updated whenever we add a dependency, voice, image or dataset; the final pass happens in Phase 8.

## Libraries and frameworks

| Name | Use | Licence |
|---|---|---|
| [Pipecat](https://github.com/pipecat-ai/pipecat) / Pipecat Flows | Voice pipeline and conversation flows | BSD-2-Clause |
| [FastAPI](https://fastapi.tiangolo.com/) | Backend API | MIT |
| [psycopg 3](https://www.psycopg.org/) + psycopg_pool | Postgres driver and async pool | LGPL-3.0 |
| [Uvicorn](https://www.uvicorn.org/) | ASGI server | BSD-3-Clause |
| [pydantic-settings](https://github.com/pydantic/pydantic-settings) | Settings from env | MIT |
| [OpenAI Python SDK](https://github.com/openai/openai-python) | Client for any OpenAI-compatible LLM API | Apache-2.0 |
| [HTTPX](https://www.python-httpx.org/), [pytest-asyncio](https://github.com/pytest-dev/pytest-asyncio) | API tests | BSD-3-Clause / Apache-2.0 |
| [python-dotenv](https://github.com/theskumar/python-dotenv) | Loads `.env` | BSD-3-Clause |
| [PostgreSQL](https://www.postgresql.org/) | Database (via Supabase) | PostgreSQL Licence |
| [Pydantic](https://docs.pydantic.dev/) | Data validation | MIT |
| [rapidfuzz](https://github.com/rapidfuzz/RapidFuzz) | Fuzzy matching of areas, names, phrases | MIT |
| [dateparser](https://github.com/scrapinghub/dateparser) | Date/time parsing | BSD-3-Clause |
| [Supabase](https://supabase.com/) (Postgres, Realtime, client libraries) | Database and live updates | Apache-2.0 / MIT |
| [Next.js](https://nextjs.org/), React | Websites | MIT |
| Tailwind CSS, shadcn/ui, Lucide, Framer Motion, React Three Fiber, Recharts, Zustand | UI, icons, motion, 3D orb, charts, state | MIT / ISC |
| pytest, Playwright, ruff, mypy, uv | Testing and tooling | MIT / Apache-2.0 |

_Exact versions are pinned in `uv.lock` and `frontend/package-lock` once those exist._

## Services and APIs

| Service | Use | Notes |
|---|---|---|
| Twilio Programmable Voice, Media Streams, WhatsApp sandbox, SMS | Phone calls and confirmations | Trial account |
| Sarvam AI | Speech-to-text (and TTS candidate, Bulbul voices) | |
| LLM provider (OpenAI-compatible API) | Conversation | Phase 3: Featherless serving `Qwen/Qwen3-30B-A3B-Instruct-2507` (Qwen model, Apache-2.0); see EVAL.md |
| Razorpay / Stripe | Payment links | Test mode only |
| Vercel, Fly.io / Render / Railway | Hosting | |

## Voices

_TTS voices used in the demo are listed here after the blind voice test._

## Images and media

No real restaurant or hospital photos or logos are used. Hero images are licence-free or generated; each one is credited here with its source and licence.

| File | Source | Licence |
|---|---|---|
| _none yet_ | | |

## Data

All businesses, doctors, ratings, addresses and bookings are **fictional sample data** created for this demo. The current files in `data/` are a placeholder set produced with Claude Code (a one-off generator script, then checked by `scripts/validate_data.py`); the final set will be generated with ChatGPT using `docs/DATA_PROMPT.md` and reviewed by the team. Any resemblance of an invented business or person name to a real one is unintended. Area names (Jubilee Hills, Gachibowli and neighbouring areas) are real Hyderabad localities used only as locations.
