"""Replay data/test_calls.json through the real flows + tools + LLM (text, no audio).

    uv run python -m backend.eval.eval                     # all 40 calls, LLM from .env
    uv run python -m backend.eval.eval --only T01,T21 -v   # a few, with transcripts
    uv run python -m backend.eval.eval --real-clock        # don't freeze "now"

"Now" is frozen at 09:00 IST today (`--now`) in Python and in every eval database, because
several test calls book "today" (e.g. T05 at 12:30) and must not depend on when you run it.

Every call gets its own freshly seeded throwaway database (never the dev/demo DB). Prints a
markdown table split by te-en / hi-en / en-IN and saves JSON to backend/eval/results/.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from datetime import datetime
from datetime import time as dtime
from pathlib import Path
from typing import Any

from backend import clock
from backend.api.deps import Services
from backend.catalog.loader import load_catalog
from backend.catalog.models import Catalog, TestCall
from backend.clock import IST, today_ist
from backend.config import Settings, get_settings
from backend.devdb import clone, ephemeral_cluster, freeze_db, make_template
from backend.eval.scoring import CaseResult, markdown_table, score, summarize
from backend.flows.session import Session
from backend.messaging import MockMessenger
from backend.store import Store
from backend.voice.llm import LLM, from_env

RESULTS_DIR = Path(__file__).resolve().parent / "results"


async def run_case(admin_url: str, case: TestCall, llm: LLM, catalog: Catalog, settings: Settings) -> CaseResult:
    name = f"eval_{case.test_id.lower()}"
    db = clone(admin_url, name)
    frozen = clock.frozen_at()
    if frozen is not None:
        freeze_db(admin_url, name, frozen)
    store = Store(db, min_size=1, max_size=3)
    await store.open()
    try:
        svc = Services(settings=settings, store=store, catalog=catalog, messenger=MockMessenger())
        session = Session(svc, llm, phone=f"+91900000{case.test_id[1:]:0>4}")
        await session.start()
        error = None
        for line in case.caller_turns:
            if session.ctx.ended:
                break
            try:
                await session.handle(line)
            except Exception as e:  # noqa: BLE001 - record and score what happened so far
                error = f"{type(e).__name__}: {e}"
                break
        await session.end()
        booking = await store.fetchrow(
            "select * from public.bookings where status <> 'cancelled' order by created_at limit 1"
        )
        result = score(case, session.ctx, booking, today_ist())
        result.error = error
        result.tools = [
            f"{e['tool']}({json.dumps(e['args'], ensure_ascii=False)}) → {e['summary']}" for e in session.tools.timeline
        ]
        if error:
            result.reasons.append(error)
        return result
    finally:
        await store.close()


async def run_all(
    cases: list[TestCall], concurrency: int, llm: LLM, catalog: Catalog, settings: Settings, admin_url: str
) -> list[CaseResult]:
    sem = asyncio.Semaphore(concurrency)
    done = 0

    async def one(case: TestCall) -> CaseResult:
        nonlocal done
        async with sem:
            r = await run_case(admin_url, case, llm, catalog, settings)
        done += 1
        mark = "✓" if r.passed else "✗"
        print(
            f"  [{done:>2}/{len(cases)}] {mark} {case.test_id} {case.language_mix:5} {case.scenario:20}"
            f" → {r.actual_outcome}" + (f"  ({'; '.join(r.reasons)})" if r.reasons and not r.passed else ""),
            flush=True,
        )
        return r

    return list(await asyncio.gather(*(one(c) for c in cases)))


def report(results: list[CaseResult], model: str, seconds: float, price_in: float, price_out: float) -> dict[str, Any]:
    summary = summarize(results)
    ms = [m for r in results for m in r.llm_ms]
    tok_in = sum(r.tokens_in for r in results)
    tok_out = sum(r.tokens_out for r in results)
    cost = tok_in / 1e6 * price_in + tok_out / 1e6 * price_out
    ordered = sorted(ms)
    stats = {
        "llm_calls": len(ms),
        "llm_ms_median": round(statistics.median(ms)) if ms else 0,
        "llm_ms_p95": ordered[round(0.95 * (len(ordered) - 1))] if ordered else 0,
        "tokens_in": tok_in,
        "tokens_out": tok_out,
        "cost_usd": round(cost, 4),
        "wall_seconds": round(seconds, 1),
    }
    return {
        "summary": {k: {b: list(v) for b, v in d.items()} for k, d in summary.items()},
        "stats": stats,
        "model": model,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="comma-separated test ids, e.g. T01,T21")
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument(
        "--price-in", type=float, default=0.125, help="USD per 1M input tokens (default: Featherless Qwen3-30B-A3B)"
    )
    ap.add_argument("--price-out", type=float, default=0.45, help="USD per 1M output tokens")
    ap.add_argument("--now", default="09:00", help="IST time of day to freeze the clock at (default 09:00)")
    ap.add_argument("--real-clock", action="store_true", help="use the real clock instead of --now")
    ap.add_argument("-v", "--verbose", action="store_true", help="print transcripts of failed calls")
    args = ap.parse_args(argv)

    if not args.real_clock:
        hh, mm = (int(x) for x in args.now.split(":"))
        clock.freeze(datetime.combine(today_ist(), dtime(hh, mm), IST))
    settings = get_settings()
    catalog = load_catalog(settings.data_dir)
    cases = catalog.test_calls
    if args.only:
        wanted = {t.strip().upper() for t in args.only.split(",")}
        cases = [c for c in cases if c.test_id in wanted]
    llm = from_env()

    started = time.perf_counter()
    with ephemeral_cluster() as admin:
        make_template(admin)
        frozen = clock.frozen_at()
        when = f"clock frozen at {frozen:%Y-%m-%d %H:%M} IST" if frozen else "real clock"
        print(f"Running {len(cases)} calls · model {settings.llm_model} · concurrency {args.concurrency} · {when}")
        results = asyncio.run(run_all(cases, args.concurrency, llm, catalog, settings, admin))
    elapsed = time.perf_counter() - started

    results.sort(key=lambda r: r.test_id)
    rep = report(results, settings.llm_model, elapsed, args.price_in, args.price_out)
    print("\n" + markdown_table(summarize(results)))
    s = rep["stats"]
    print(
        f"\nLLM: {s['llm_calls']} calls · median {s['llm_ms_median']} ms · p95 {s['llm_ms_p95']} ms · "
        f"{s['tokens_in']:,} in / {s['tokens_out']:,} out tokens · ≈ ${s['cost_usd']} · {s['wall_seconds']} s"
    )

    if args.verbose:
        for r in results:
            if not r.passed:
                print(f"\n--- {r.test_id} ({'; '.join(r.reasons)}) ---")
                for line in r.transcript:
                    print(f"  {line['speaker']:6} [{line['lang']}] {line['text']}")

    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(IST).strftime("%Y%m%d-%H%M")
    payload = {
        **rep,
        "run_at": datetime.now(IST).isoformat(timespec="seconds"),
        "clock_frozen_at": frozen.isoformat() if frozen else None,
        "cases": [r.to_json() for r in results],
    }
    for name in (f"eval-{stamp}.json", "latest.json"):
        (RESULTS_DIR / name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )
    print(f"\nSaved backend/eval/results/eval-{stamp}.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
