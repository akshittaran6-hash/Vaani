"""Chat with Vaani in text (the same flows the phone uses, minus audio).

    uv run python -m backend.flows.cli                 # throwaway seeded DB, LLM from .env
    uv run python -m backend.flows.cli --db-url URL    # an existing DB you are happy to write bookings to

Type 'bye' or Ctrl-D to end the call; the outcome JSON is printed at the end.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from contextlib import ExitStack

from backend.api.deps import Services
from backend.catalog.loader import load_catalog
from backend.config import get_settings
from backend.devdb import clone, ephemeral_cluster, make_template
from backend.flows.session import Session
from backend.messaging import MockMessenger
from backend.store import Store
from backend.voice.llm import from_env

DIM, BOLD, RESET = "\033[2m", "\033[1m", "\033[0m"


async def chat(db_url: str, phone: str) -> None:
    settings = get_settings()
    store = Store(db_url, max_size=4)
    await store.open()
    messenger = MockMessenger()
    svc = Services(settings=settings, store=store, catalog=load_catalog(settings.data_dir), messenger=messenger)
    session = Session(svc, from_env(), phone=phone)
    print(f"{BOLD}Vaani:{RESET} {await session.start()}")
    seen = 0
    try:
        while not session.ctx.ended:
            try:
                text = input(f"{BOLD}You:{RESET} ").strip()
            except EOFError:
                break
            if not text:
                continue
            if text.lower() in {"bye", "quit", "exit"}:
                break
            turn = await session.handle(text)
            for entry in session.tools.timeline[seen:]:
                print(f"{DIM}  · {entry['summary']} ({entry['ms']} ms){RESET}")
            seen = len(session.tools.timeline)
            print(f"{BOLD}Vaani:{RESET} {turn.reply}")
        for m in messenger.sent:
            print(f"{DIM}--- {m.channel} to {m.to} ---\n{m.body}{RESET}")
        print(json.dumps(await session.end(), indent=2, ensure_ascii=False, default=str))
    finally:
        await store.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db-url", help="use this database (bookings are written to it); default: throwaway DB")
    ap.add_argument("--phone", default="+919000000001", help="pretend caller ID")
    args = ap.parse_args(argv)
    with ExitStack() as stack:
        url = args.db_url
        if not url:
            print(f"{DIM}Starting a throwaway database…{RESET}", file=sys.stderr)
            admin = stack.enter_context(ephemeral_cluster())
            make_template(admin)
            url = clone(admin, "vaani_cli")
        asyncio.run(chat(url, args.phone))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
