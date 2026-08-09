"""
Focus-plan builder: prioritises curriculum days to ask about, based on
the candidate's mission history.

Tier 1 (ask first):  skipped == true  OR  passed == false
Tier 2 (ask next):   passed == true  AND  attempts >= 3  (struggled)
Tier 3 (stretch):    passed == true  AND  attempts == 1  (fast pass)

Interleaved so it doesn't read as an obvious "weak-points first" script.
If the plan covers fewer than 4 distinct days, backfill from curriculum
with days the candidate hasn't attempted.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

# ─── Module-level data loading (once, at import time) ────────────────

_DATA_DIR = pathlib.Path(__file__).resolve().parent.parent / "data"

with open(_DATA_DIR / "curriculum.json", encoding="utf-8") as _f:
    CURRICULUM: dict = json.load(_f)

with open(_DATA_DIR / "candidates.json", encoding="utf-8") as _f:
    CANDIDATES: dict = json.load(_f)

# day number → full day object  {day, title, type, tools[], objectives[]}
DAY_LOOKUP: dict[int, dict] = {d["day"]: d for d in CURRICULUM["days"]}

# day number → module number
DAY_TO_MODULE: dict[int, int] = {}
for _mod in CURRICULUM["modules"]:
    for _d in range(_mod["days"][0], _mod["days"][1] + 1):
        DAY_TO_MODULE[_d] = _mod["n"]


# ─── Public API ──────────────────────────────────────────────────────

def build_focus_plan(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    """Return an ordered list of focus-plan entries for the interview.

    Each entry:
        {day, tier, title, type, tools, objectives, moduleN, reason}
    """
    missions = candidate.get("missions", [])

    tier1: list[dict] = []  # skipped or failed
    tier2: list[dict] = []  # struggled but passed (attempts >= 3)
    tier3: list[dict] = []  # fast pass (attempts == 1)

    attempted_days: set[int] = set()

    for m in missions:
        day = m["day"]
        attempted_days.add(day)

        if m.get("skipped"):
            tier1.append(_make_entry(day, 1, "Skipped mission"))
        elif not m.get("passed", False):
            attempts = m.get("attempts", 0)
            tier1.append(_make_entry(day, 1, f"Did not pass (attempted {attempts}×)"))
        elif m.get("attempts", 1) >= 3:
            attempts = m["attempts"]
            tier2.append(_make_entry(day, 2, f"Struggled but passed ({attempts} attempts)"))
        elif m.get("attempts", 1) == 1:
            tier3.append(_make_entry(day, 3, "Fast pass — stretch question"))

    # Interleave: 2 from Tier 1, 1 from Tier 2, repeat; then remaining + Tier 3
    plan = _interleave(tier1, tier2, tier3)

    # Guarantee at least 4 distinct curriculum days
    plan_days = {e["day"] for e in plan}
    if len(plan_days) < 4:
        _backfill(plan, plan_days, attempted_days)

    return plan


# ─── Helpers ─────────────────────────────────────────────────────────

def _make_entry(day: int, tier: int, reason: str) -> dict[str, Any]:
    """Build a single focus-plan entry by enriching with curriculum data."""
    day_info = DAY_LOOKUP.get(day, {})
    return {
        "day": day,
        "tier": tier,
        "title": day_info.get("title", f"Day {day}"),
        "type": day_info.get("type", "UNKNOWN"),
        "tools": day_info.get("tools", []),
        "objectives": day_info.get("objectives", []),
        "moduleN": DAY_TO_MODULE.get(day, 0),
        "reason": reason,
    }


def _interleave(
    tier1: list[dict],
    tier2: list[dict],
    tier3: list[dict],
) -> list[dict]:
    """Interleave tiers so the interview doesn't feel like a weakness drill.

    Pattern: pick 2 from T1, 1 from T2, repeat.  Then append leftovers
    from whichever tier still has items.  Tier 3 goes at the end.
    """
    result: list[dict] = []
    i1, i2 = 0, 0

    while i1 < len(tier1) or i2 < len(tier2):
        # Take up to 2 from tier1
        for _ in range(2):
            if i1 < len(tier1):
                result.append(tier1[i1])
                i1 += 1

        # Take 1 from tier2
        if i2 < len(tier2):
            result.append(tier2[i2])
            i2 += 1

    # Tier 3 (stretch) appended at the end
    result.extend(tier3)
    return result


def _backfill(
    plan: list[dict],
    plan_days: set[int],
    attempted_days: set[int],
) -> None:
    """Add unattempted curriculum days until we have ≥ 4 distinct days."""
    all_days = sorted(DAY_LOOKUP.keys())
    for day in all_days:
        if len(plan_days) >= 4:
            break
        if day not in plan_days and day not in attempted_days:
            entry = _make_entry(day, 2, "Unattempted — let's see what you know here")
            plan.append(entry)
            plan_days.add(day)
