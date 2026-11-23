"""Convert a teammate's generated data folder into the shape of CONTRACTS.md §7, then validate it.

    uv run python scripts/import_data.py ~/Downloads            # writes data/
    uv run python scripts/import_data.py ~/Downloads --out /tmp/x --dry-run

What it changes (content is never edited, only shape):
- drops `is_sample_data` where the contract has no such field (availability rows, test calls,
  agent phrases, phrase lists); keeps it on areas / businesses / doctors;
- `areas.json` given as `{"areas": [...], "unsupported_area_reply": {...}}` → a list, with the
  shared reply copied into each area; aliases lower-cased;
- `speciality_mapping.json` key `mappings` → `phrases`;
- missing `slug` (name + area, e.g. `dumgalli-courtyard-jubilee-hills`) and `accent_color`
  (a stable pick from a fixed palette by name) on restaurants and hospitals;
- missing test-call `scenario`, inferred from the expected outcome and the caller's words;
- merges the baseline phrases in `scripts/data_extras/speciality_base.json` into
  `speciality_mapping.json` (short common forms like "chest pain", "सीने में दर्द", "heart doctor";
  the teammate's phrases win when the same phrase maps to a different speciality).

Run it again whenever the source files are regenerated; it's idempotent on already-converted data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.catalog.loader import DATA_DIR, FILES, CatalogLoadError, load_catalog  # noqa: E402
from backend.catalog.validate import validate_catalog  # noqa: E402

# Muted, readable accents (light and dark UI); picked by a hash of the name so they're stable.
PALETTE = (
    "#C2410C", "#B45309", "#A16207", "#4D7C0F", "#15803D", "#047857", "#0F766E", "#0E7490",
    "#0369A1", "#1D4ED8", "#4338CA", "#6D28D9", "#7E22CE", "#A21CAF", "#BE185D", "#BE123C",
)

BASE_PHRASES = Path(__file__).resolve().parent / "data_extras" / "speciality_base.json"

CHANGE_WORDS = ("actually", "change that", "instead", "maarchandi", "kaadu", "badal", "nahi,")


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def accent_for(name: str) -> str:
    digest = hashlib.sha256(name.encode("utf-8")).digest()
    return PALETTE[digest[0] % len(PALETTE)]


def _strip_flag(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{k: v for k, v in row.items() if k != "is_sample_data"} for row in rows]


def convert_areas(raw: Any) -> list[dict[str, Any]]:
    rows = raw if isinstance(raw, list) else raw["areas"]
    reply = None if isinstance(raw, list) else raw.get("unsupported_area_reply")
    # Aliases are matched lower-cased (lower() leaves Telugu/Devanagari unchanged).
    return [
        {
            **a,
            "aliases": list(dict.fromkeys(x.lower() for x in a["aliases"])),
            "unsupported_area_reply": a.get("unsupported_area_reply", reply),
        }
        for a in rows
    ]


def add_slug_and_accent(rows: list[dict[str, Any]], area_names: dict[str, str]) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        row = dict(row)
        row.setdefault("slug", slugify(f"{row['name']} {area_names.get(row['area_id'], row['area_id'])}"))
        row.setdefault("accent_color", accent_for(row["name"]))
        out.append(row)
    return out


def infer_scenario(call: dict[str, Any], max_party: dict[str, int]) -> str:
    exp = call["expected"]
    words = " ".join(call["caller_turns"]).lower()
    outcome = exp["outcome"]
    if outcome == "declined_unsupported_area":
        return "unsupported_area"
    if outcome == "redirected_emergency":
        return "emergency"
    if outcome == "answered_faq":
        return "faq"
    party = exp.get("party_size")
    if call["service"] == "restaurant" and party and party > max_party.get(exp.get("business_id") or "", 99):
        return "party_limit"
    if "deposit" in words:
        return "deposit_needed"
    if call["service"] == "hospital" and ("full" in words or outcome == "offered_alternatives"):
        return "doctor_fully_booked"
    if "full" in words or outcome == "offered_alternatives":
        return "slot_full"
    if any(w in words for w in CHANGE_WORDS):
        return "mid_call_change"
    return "happy_path"


def _phrase_key(row: dict[str, Any]) -> tuple[str, str]:
    return (" ".join(row["phrase"].lower().split()), row["lang"])


def merge_phrases(spec: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    """Add baseline phrases that the teammate's file doesn't already have (by phrase + lang)."""
    out = dict(spec)
    for key in ("phrases", "emergency_phrases"):
        rows = list(spec[key])
        seen = {_phrase_key(r) for r in rows}
        if key == "phrases":
            # A baseline phrase that is an emergency in the teammate's file must not become a speciality.
            seen |= {_phrase_key(r) for r in spec["emergency_phrases"]}
        else:
            seen |= {_phrase_key(r) for r in spec["phrases"]}
        rows += [r for r in base.get(key, []) if _phrase_key(r) not in seen]
        out[key] = rows
    return out


def convert(src: dict[str, Any], base_phrases: dict[str, Any] | None = None) -> dict[str, Any]:
    areas = convert_areas(src["areas"])
    area_names = {a["area_id"]: a["name_en"] for a in areas}
    restaurants = add_slug_and_accent(src["restaurants"], area_names)
    max_party = {r["restaurant_id"]: r["booking_rules"]["max_party_size"] for r in restaurants}

    spec = dict(src["speciality_mapping"])
    if "mappings" in spec and "phrases" not in spec:
        spec["phrases"] = spec.pop("mappings")
    spec["phrases"] = _strip_flag(spec["phrases"])
    spec["emergency_phrases"] = _strip_flag(spec["emergency_phrases"])
    if base_phrases:
        spec = merge_phrases(spec, base_phrases)

    calls = []
    for c in _strip_flag(src["test_calls"]):
        if "scenario" not in c:
            # Keep the contract's key order: scenario sits after language_mix.
            c = {k: v for k, v in c.items() if k not in ("caller_turns", "expected")} | {
                "scenario": infer_scenario(c, max_party),
                "caller_turns": c["caller_turns"],
                "expected": c["expected"],
            }
        calls.append(c)

    return {
        "areas": areas,
        "restaurants": restaurants,
        "restaurant_availability": _strip_flag(src["restaurant_availability"]),
        "hospitals": add_slug_and_accent(src["hospitals"], area_names),
        "doctors": src["doctors"],
        "doctor_availability": _strip_flag(src["doctor_availability"]),
        "speciality_mapping": spec,
        "test_calls": calls,
        "agent_phrases": _strip_flag(src["agent_phrases"]),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", type=Path, help="folder with the 9 generated JSON files")
    ap.add_argument("--out", type=Path, default=DATA_DIR)
    ap.add_argument("--no-base-phrases", action="store_true", help="don't merge scripts/data_extras phrases")
    ap.add_argument("--dry-run", action="store_true", help="convert and validate in memory; write nothing")
    args = ap.parse_args(argv)

    missing = [f"{stem}.json" for stem in FILES if not (args.src / f"{stem}.json").exists()]
    if missing:
        print(f"✗ missing in {args.src}: {', '.join(missing)}")
        return 1
    src = {stem: json.loads((args.src / f"{stem}.json").read_text(encoding="utf-8")) for stem in FILES}
    base = None if args.no_base_phrases else json.loads(BASE_PHRASES.read_text(encoding="utf-8"))
    out = convert(src, base)
    spec = out["speciality_mapping"]
    print(f"  {len(spec['phrases'])} speciality phrases, {len(spec['emergency_phrases'])} emergency phrases")

    target = args.out
    if args.dry_run:
        import tempfile

        target = Path(tempfile.mkdtemp(prefix="vaani-import-"))
    target.mkdir(parents=True, exist_ok=True)
    for stem, value in out.items():
        text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
        (target / f"{stem}.json").write_text(text, encoding="utf-8")

    try:
        report = validate_catalog(load_catalog(target))
    except CatalogLoadError as e:
        print(f"✗ {len(e.problems)} shape problem(s) after conversion:")
        for p in e.problems[:50]:
            print(f"  - {p}")
        return 1
    for w in report.warnings:
        print(f"  ! {w}")
    for err in report.errors:
        print(f"  ✗ {err}")
    verb = "checked (dry run)" if args.dry_run else f"written to {target}"
    status = "✗ INVALID" if report.errors else "✓ OK"
    print(f"{status} — {len(report.errors)} error(s), {len(report.warnings)} warning(s); {verb}")
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
