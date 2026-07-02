"""
Tests for the STAY foundation (build commit 1 of addendum §8.5.8). No pytest:
    python3 test_stay.py

Both directions, per the plan:
  - park's 9 "Al.Mat" rows become held stays with the §13.4 arithmetic
    (41 expected / 23 named / 18 pending), NOT guests;
  - a park twin is ONE stay carrying TWO guests, identity intact;
  - zero real guests are ever misclassified as held capacity — recognition is
    narrow (a pax-count is required; mixed rows fall through to the guard);
  - mix18 and polish are unchanged at guest level and reconcile as complete;
  - guests without a stay link (the bespoke parser) count 1-for-1, so legacy
    paths never read as pending;
  - content the map cannot see becomes an `unrecognized` stay that BLOCKS
    completeness — the categorical floor (PLAN-dispatch-floor.md).

Dev lists only; holdout sealed.
"""
from maps import (read_docx_rows, read_xlsx_rows, MIX18_DOCX, POLISH_XLSX,
                  MIX18_MAP, POLISH_MAP, parse_park_stays)
from parse_mix18 import parse as parse_bespoke
from parser import transcribe_with_stays, ColumnMap, NameSlot
from stay import Stay, held_pax, reconcile, completeness_status
from validate import validate_guest, is_submittable


# --- the recognizer: narrow, both directions ---------------------------------
def test_held_recognizer():
    held = {"Al.Mat. arrivi 18 pax": 18, "Al.Mat. arrivi 17 pax": 17,
            "18 pax": 18, "2 PAX": 2, "arrivi 3  pax": 3,
            "+ 2 autisti": 2, "1 autista": 1}
    for text, n in held.items():
        assert held_pax(text) == n, f"should recognize {text!r} as {n}"

    # NOT held: no count, no 'pax' token, or 'pax' inside a real name
    not_held = ["Driver 1", "Driver 2", "2 drivers",   # driver = index, not a count
                "SGL", "DBL", "No. of rooms / people",
                "names pending", "TBD", "PAXTON", "PAXTON Jim", "KOVALCHUK",
                "GUIDE NOWAK", "", "1234 paxton"]
    for text in not_held:
        assert held_pax(text) is None, f"false positive: {text!r}"
    print("PASS recognizer: pax-counts caught, names/count-less placeholders refused")


# --- park end-to-end: the §13.4 arithmetic ------------------------------------
def test_park_reconciliation():
    res = parse_park_stays()
    held = [s for s in res.stays if s.status == "names_pending"]
    named = [s for s in res.stays if s.status == "complete"]

    assert len(res.guests) == 23 and len(held) == 9 and len(named) == 19
    assert sum(s.pax_expected for s in held) == 18, "9 held twins = 18 pax"
    assert sum(held_pax(s.verbatim) for s in held) == 161, \
        "text-N restates BLOCK totals (8x18 + 17) — advisory in-slot, never summed"
    assert all(s.verbatim.startswith("Al.Mat") for s in held), \
        "held stays must keep the source text verbatim (§8.5.7)"
    assert all(s.source_row is not None for s in res.stays), "provenance required"

    rec = reconcile(res.stays, res.guests)
    assert rec == {"expected": 41, "named": 23, "pending": 18, "overage": 0,
                   "unrecognized": 0}, rec
    assert completeness_status(rec) == "awaiting_completion"

    # a twin is ONE stay with TWO guests, identity intact and distinct
    by_stay = {}
    for g in res.guests:
        by_stay.setdefault(g.stay_id, []).append(g)
    twins = [gs for gs in by_stay.values() if len(gs) == 2]
    singles = [gs for gs in by_stay.values() if len(gs) == 1]
    assert len(twins) == 4 and len(singles) == 15, \
        f"park is 15 singles + 4 named twins, got {len(singles)}/{len(twins)}"
    for pair in twins:
        assert pair[0].cognome != pair[1].cognome, "twin guests must be two people"
    # every guest sits on a real, NAMED stay; no guest on a held stay
    stay_ids = {s.stay_id for s in named}
    assert all(g.stay_id in stay_ids for g in res.guests)
    print("PASS park: 23 guests / 9 held stays -> 41 expected, 23 named, "
          "18 pending, awaiting_completion; twins = one stay, two guests")


# --- zero real guests misclassified; mixed rows go to the guard ---------------
def test_mixed_row_is_not_held():
    rows = [["h", "h", "h", "h"],
            ["ROSSI", "Mario", "2 pax", ""],       # real name + placeholder slot
            ["Al.Mat. arrivi 18 pax", "", "", ""]] # pure placeholder row
    cmap = ColumnMap(header_rows=1, default_role="20",
                     name_slots=[NameSlot(surname_column=0, firstname_column=1),
                                 NameSlot(surname_column=2, firstname_column=3)])
    res = transcribe_with_stays(rows, cmap)

    held = [s for s in res.stays if s.status == "names_pending"]
    assert len(held) == 1 and held[0].verbatim == "Al.Mat. arrivi 18 pax"
    # the mixed row emitted BOTH slots as guests: ROSSI clean, "2 pax" guard-red
    assert [g.cognome for g in res.guests] == ["ROSSI", "2 pax"]
    rossi, placeholder = res.guests
    assert rossi.stay_id == placeholder.stay_id, "same row -> same stay"
    # ROSSI is a real guest (other fields missing aside): his NAME must be clean
    assert not any("non sembra un nome" in i.message for i in validate_guest(rossi)
                   if i.field == "cognome")
    assert any("non sembra un nome" in i.message for i in validate_guest(placeholder))
    assert not is_submittable(placeholder)
    print("PASS mixed row -> guests (guard reds the placeholder slot), never held")


# --- reconcile math units (incl. overage, advisory only) ----------------------
def test_reconcile_units():
    class G:  # minimal duck-typed guest
        def __init__(self, sid): self.stay_id = sid
    stays = [Stay(stay_id=1, pax_expected=2, status="complete"),
             Stay(stay_id=2, pax_expected=18, status="names_pending"),
             Stay(stay_id=3, pax_expected=1, status="complete")]
    guests = [G(1), G(1), G(3), G(3)]           # stay 3 overfilled (2 on a single)
    rec = reconcile(stays, guests)
    assert rec == {"expected": 21, "named": 4, "pending": 18, "overage": 1,
                   "unrecognized": 0}, rec
    assert completeness_status(rec) == "awaiting_completion"
    # overage alone must NOT block completeness (advisory, §8.5.2)
    rec2 = reconcile([stays[2]], [G(3), G(3)])
    assert rec2 == {"expected": 1, "named": 2, "pending": 0, "overage": 1,
                    "unrecognized": 0}
    assert completeness_status(rec2) == "complete"
    print("PASS reconcile units: per-stay pending/overage; overage never blocks")


# --- the floor: unseen content never vanishes, never becomes phantom pax -------
def test_residue_floor():
    rows = [["h", "h", "h"],
            ["", "", ""],                              # truly blank -> nothing
            ["Totale: 47", "", ""],                    # residue, NO held vocabulary
            ["+ 2 autisti", "", ""],                   # residue, held vocabulary
            ["nota: fatture al capogruppo", "", ""]]   # residue prose
    cmap = ColumnMap(header_rows=1, default_role="20",
                     name_slots=[NameSlot(surname_column=1, firstname_column=2)])
    res = transcribe_with_stays(rows, cmap)

    assert res.guests == [], "residue must never fabricate guests"
    kinds = [(s.status, s.pax_expected, s.verbatim) for s in res.stays]
    assert kinds == [("unrecognized", 0, "Totale: 47"),
                     ("names_pending", 2, "+ 2 autisti"),
                     ("unrecognized", 0, "nota: fatture al capogruppo")], kinds
    assert all(s.source_row is not None for s in res.stays), "provenance required"

    rec = reconcile(res.stays, res.guests)
    assert rec == {"expected": 2, "named": 0, "pending": 2, "overage": 0,
                   "unrecognized": 2}, rec
    assert completeness_status(rec) == "awaiting_completion"

    # the floor alone blocks complete, even at zero pending
    only_unrec = [s for s in res.stays if s.status == "unrecognized"]
    rec2 = reconcile(only_unrec, [])
    assert rec2["pending"] == 0 and rec2["unrecognized"] == 2
    assert completeness_status(rec2) == "awaiting_completion", \
        "an unrecognized row must block complete on its own"
    print("PASS residue floor: 'Totale: 47' -> unrecognized (never held-47, "
          "never dropped); unrecognized alone blocks complete")


# --- the other dev lists: unchanged and complete -------------------------------
def test_other_lists_complete():
    m = transcribe_with_stays(read_docx_rows(MIX18_DOCX), MIX18_MAP)
    assert len(m.guests) == 39 and len(m.stays) == 39      # one slot per row
    assert not [s for s in m.stays if s.status == "unrecognized"]
    assert completeness_status(reconcile(m.stays, m.guests)) == "complete"

    # polish's two non-emitting rows are TRULY EMPTY (census in the plan) —
    # the floor must not invent stays for them
    p = transcribe_with_stays(read_xlsx_rows(POLISH_XLSX), POLISH_MAP)
    assert len(p.guests) == 55 and len(p.stays) == 55
    assert not [s for s in p.stays if s.status == "unrecognized"]
    assert not [s for s in p.stays if s.status == "names_pending"]
    assert completeness_status(reconcile(p.stays, p.guests)) == "complete"

    # legacy fallback: bespoke guests carry stay_id=None and count 1-for-1
    legacy = [w.guest for w in parse_bespoke()]
    rec = reconcile([], legacy)
    assert rec == {"expected": 39, "named": 39, "pending": 0, "overage": 0,
                   "unrecognized": 0}
    assert completeness_status(rec) == "complete"
    print("PASS mix18 (39/39) + polish (55, no held) complete; "
          "legacy unlinked guests never read as pending")


if __name__ == "__main__":
    test_held_recognizer()
    test_park_reconciliation()
    test_mixed_row_is_not_held()
    test_residue_floor()
    test_reconcile_units()
    test_other_lists_complete()
    print("ALL GREEN")
