"""
Soglia — the STAY entity (rooms / held capacity) + reconciliation (§8.5.2).

Build commit 1 of addendum §8.5.8. Identity stays on Guest; a Stay is the
room-shaped unit a row describes — one Stay per guest-yielding or held row.
Held-capacity recognition is DETERMINISTIC code, never model/map-authored:
a held row must be caught even when stage 1's sample window never saw one,
and it takes precedence over any map-authored skip rule.

pax_expected derivation (v1, deliberate — see PLAN-stay-foundation.md §1):
  - a NAMED row's stay expects exactly its filled name slots (a park twin = 2);
  - a HELD row expects the row's name-slot capacity (len(map.name_slots)) —
    NOT the number in the placeholder text. The source restates the BLOCK
    total on every room row ("Al.Mat. arrivi 18 pax" x8 + "...17 pax" x1),
    so summing text-N gives 161; slot capacity gives 9 x 2 = 18, matching
    handoff §13.4's arithmetic (41 expected / 23 named / 18 pending). The
    text is kept VERBATIM on the stay (§8.5.7: nothing vanishes unreviewably).
  Room-type-derived occupancy is a named follow-up (needs a mapped column,
  which changes the frozen stage-1 ColumnMap contract).
"""
import re
from dataclasses import dataclass

# "<N> pax" as whole tokens, case-insensitive: catches "Al.Mat. arrivi 18 pax"
# and "2 pax"; does NOT catch "Driver 1" (no pax), "PAXTON" (word boundary),
# "SGL" / "No. of rooms" (no count), or "names pending" (no count — a held
# stay with unknowable pax must not feed arithmetic that could read as
# complete, so count-less placeholders stay guard-red guests instead).
# Known bounded edge (review finding): a single cell mixing a full personal
# name with a count ("ROSSI Mario 2 pax") classifies as held — the list can
# never read complete and the verbatim is preserved for review, but the name
# bypasses the guest list; the room-type-column follow-up is the structural fix.
_HELD = re.compile(r"\b(\d{1,3})\s*pax\b", re.IGNORECASE)


def held_pax(text: str):
    """Return the block count if `text` is a pax-count placeholder, else None.

    The count is ADVISORY (it is the block total, not the row's occupancy):
    it serves as the recognition signal and review context, and is never
    summed into reconciliation.
    """
    m = _HELD.search(text)
    return int(m.group(1)) if m else None


@dataclass
class Stay:
    """One room-shaped unit of a list. Minimal on purpose — only the fields
    this commit exercises; room/room_type arrive with the mapped-column
    follow-up rather than sitting here dead."""
    stay_id: int                 # per-transcription id; Guest.stay_id joins here
    pax_expected: int
    status: str                  # "names_pending" | "complete" ("over": supplements, later)
    verbatim: str = ""           # held rows: the source cell text, for review
    source_row: int = None       # 0-based row index in the source table (provenance)


def reconcile(stays, guests) -> dict:
    """§8.5.2, PAX-aware: per-stay pending/overage, summed to list totals.

    Guests without a stay link (the bespoke mix18 parser, hand-built fixtures)
    count 1-for-1 — expected and named both grow — so a legacy path can never
    read as pending, and a held room can never silently read as complete.
    """
    linked = {}
    for g in guests:
        sid = getattr(g, "stay_id", None)
        if sid is not None:
            linked[sid] = linked.get(sid, 0) + 1

    expected = named = pending = overage = 0
    for s in stays:
        n = linked.get(s.stay_id, 0)
        expected += s.pax_expected
        named += n
        pending += max(0, s.pax_expected - n)
        overage += max(0, n - s.pax_expected)

    unlinked = sum(1 for g in guests if getattr(g, "stay_id", None) is None)
    expected += unlinked
    named += unlinked
    return {"expected": expected, "named": named, "pending": pending, "overage": overage}


def completeness_status(reconciliation: dict) -> str:
    """§8.5.1 completeness axis. Overage is advisory and NON-blocking; the
    override state (complete_by_override) arrives with the audit commit (4)."""
    return "complete" if reconciliation["pending"] == 0 else "awaiting_completion"
