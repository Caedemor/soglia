"""
Soglia — the STAY entity (rooms / held capacity) + reconciliation (§8.5.2).

Build commit 1 of addendum §8.5.8. Identity stays on Guest; a Stay is the
room-shaped unit a row describes — one Stay per guest-yielding or held row.
Held-capacity recognition is DETERMINISTIC code, never model/map-authored:
a held row must be caught even when stage 1's sample window never saw one,
and it takes precedence over any map-authored skip rule.

pax_expected derivation (v1, deliberate — see PLAN-stay-foundation.md §1):
  - a NAMED row's stay expects exactly its filled name slots (a park twin = 2);
  - a HELD row IN the name slots expects the row's name-slot capacity
    (len(map.name_slots)) — NOT the number in the placeholder text. The source restates the BLOCK
    total on every room row ("Al.Mat. arrivi 18 pax" x8 + "...17 pax" x1),
    so summing text-N gives 161; slot capacity gives 9 x 2 = 18, matching
    handoff §13.4's arithmetic (41 expected / 23 named / 18 pending). The
    text is kept VERBATIM on the stay (§8.5.7: nothing vanishes unreviewably).
  - a RESIDUE held row (no slot structure at all, e.g. a "+ 2 autisti"
    trailer) takes the text's N as AUTHORITATIVE — there are no slots to
    count (see PLAN-dispatch-floor.md);
  - any OTHER residue row becomes an `unrecognized` stay (pax 0) that BLOCKS
    completeness: the categorical floor underneath the vocabulary.
  Room-type-derived occupancy is a named follow-up (needs a mapped column,
  which changes the frozen stage-1 ColumnMap contract).
"""
import re
from dataclasses import dataclass

# "<N> pax|autisti" as whole tokens, case-insensitive: catches "Al.Mat. arrivi
# 18 pax", "2 pax", "+ 2 autisti", "1 autista"; does NOT catch "Driver 1" or
# "2 drivers" — "driver" is deliberately OUT: "Driver 2" is an INDEX, not a
# count (two such rows are two people at pax 1 each, not one row at pax 2).
# It also does not catch "PAXTON" (word boundary),
# "SGL" / "No. of rooms" (no count), or "names pending" (no count — a held
# stay with unknowable pax must not feed arithmetic that could read as
# complete, so count-less placeholders stay guard-red guests instead).
# Growing this vocabulary is NOT the safety story: residue text it doesn't
# speak lands as an `unrecognized` stay that blocks completeness (the floor,
# parser.py). Documented sharp edge: a residue totals row containing held
# vocabulary ("47 pax totale") reads held-47 — loudly wrong (pending 47),
# never silently complete; no denylist (that's the enumeration trap).
# Known bounded edge (review finding): a single cell mixing a full personal
# name with a count ("ROSSI Mario 2 pax") classifies as held — the list can
# never read complete and the verbatim is preserved for review, but the name
# bypasses the guest list; the room-type-column follow-up is the structural fix.
_HELD = re.compile(r"\b(\d{1,3})\s*(?:pax|autist[ai])\b", re.IGNORECASE)


def held_pax(text: str):
    """Return the count if `text` is a held-capacity placeholder, else None.

    AUTHORITY depends on where the text sits (the dispatch decides):
      - IN a name slot: ADVISORY — park restates the BLOCK total on every
        room row (naive text-sum 161 vs slot-derived truth 18), so in-slot
        held stays take pax_expected from slot capacity, never this count;
      - RESIDUE (a row with no slot content, e.g. the "+ 2 autisti" trailer):
        AUTHORITATIVE — there are no slots to count; the text's N is the pax.
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
    status: str                  # "names_pending" | "complete" | "unrecognized" ("over": later)
    verbatim: str = ""           # held rows: the source cell text, for review
    source_row: int = None       # 0-based row index in the source table (provenance)


def reconcile(stays, guests) -> dict:
    """§8.5.2, PAX-aware: per-stay pending/overage, summed to list totals.

    Guests without a stay link (the bespoke mix18 parser, hand-built fixtures)
    count 1-for-1 — expected and named both grow — so a legacy path can never
    read as pending, and a held room can never silently read as complete.
    Unrecognized stays contribute ZERO to the arithmetic (pax_expected is 0 —
    an attention count, not people); the "unrecognized" key rides along so
    completeness and the UI can see them.
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
    unrecognized = sum(1 for s in stays if s.status == "unrecognized")
    return {"expected": expected, "named": named, "pending": pending,
            "overage": overage, "unrecognized": unrecognized}


def completeness_status(reconciliation: dict) -> str:
    """§8.5.1 completeness axis. Overage is advisory and NON-blocking. An
    UNRECOGNIZED row blocks `complete` exactly like pending pax — a row the
    map cannot see must cost a human a glance, never a silent false-complete
    (the floor). The override state (complete_by_override) arrives with the
    audit commit (4)."""
    return ("complete"
            if reconciliation["pending"] == 0
            and reconciliation.get("unrecognized", 0) == 0
            else "awaiting_completion")
