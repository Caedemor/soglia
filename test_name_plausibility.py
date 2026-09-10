"""
Tests for the deterministic name-plausibility guard in validate.py.

Both directions matter equally:
  (a) the 9 held "Al.Mat. arrivi N pax" placeholder rows in the Park list are
      now caught UPSTREAM of the guard by held-capacity recognition (stay.py)
      — deterministically, on EVERY row, regardless of the map's skip rule
      (stage 1's sample window never saw them). They become names_pending
      stays, never guests. A count-less placeholder ("names pending", "TBD",
      "Driver 1") has no pax to hold, so disposition 3b routes it to an
      `unrecognized` stay instead — also never a guest. The guard remains the
      BACKSTOP for the one shape that still emits a placeholder GUEST: a MIXED
      row, where a real person shares the row with a placeholder slot;
  (b) NOT ONE real PERSONAL NAME across the four dev samples is falsely
      flagged. The guard must not cry wolf on real names — Cyrillic, Polish
      diacritics, compound given names, the honorific "Ks. KOWALCZYK", or the
      role marker "GUIDE NOWAK" are all valid and must pass.

Note: the guard's CATEGORY judgement is what the floor now consumes — it is
the same function (`validate.implausible_name`, public for exactly this) that
decides whether a row carries a person at all. The Polish "Driver N" crew
slots, a pattern we never designed for, are caught by that generalization
rather than by matching "Al.Mat".

Dev samples only (maps.py). The holdout set is never read here.
"""
import dataclasses

from validate import implausible_name, validate_guest, is_submittable
from parser import transcribe, transcribe_with_stays, ColumnMap, NameSlot
from maps import (parse_mix18, parse_polish, parse_textmail, parse_park,
                  read_xlsx_rows, PARK_XLSX, PARK_MAP,
                  POLISH_XLSX, POLISH_MAP)


def _park_no_skip():
    """The Park list WITHOUT the hand-written skip rule — i.e. exactly what the
    live model's map produced (it never inferred the held-row skip). Held
    recognition must catch the 9 'Al.Mat. arrivi N pax' rows anyway: it is
    code, not map-dependent."""
    no_skip = dataclasses.replace(PARK_MAP, skip_row=None)
    return transcribe_with_stays(read_xlsx_rows(PARK_XLSX), no_skip)


def _name_reds(g):
    """RED issues on a name field that come specifically from the plausibility gate."""
    return [i for i in validate_guest(g)
            if i.tier == "red" and i.field in ("cognome", "nome")
            and "non sembra un nome" in i.message]


def _is_placeholder_label(cognome):
    """Ground-truth labelling of the dev data, INDEPENDENT of the guard: the name
    cell is a held count/role placeholder, not a person. Used to assert the guard
    catches exactly these and nothing else."""
    c = cognome.strip().lower()
    return c.startswith("al.mat") or c.startswith("driver")


# --- unit: the heuristic on literal strings (category-based, not string-based) ---
def test_heuristic_units():
    implausible = ["Al.Mat. arrivi 18 pax", "Al.Mat. arrivi 17 pax", "18 pax",
                   "names pending", "TBD", "TOTALE", "N/A", "—", "///", "3"]
    for bad in implausible:
        assert implausible_name(bad) is not None, f"should flag: {bad!r}"

    # unusual-but-real names must pass untouched (no specific string is hardcoded)
    plausible = ["KOVALCHUK", "Ткаченко", "Ірина", "WÓJCIK", "Wiśniewski",
                 "Dąbrowski", "Zając", "Sikora", "Tomasz Grzegorz",
                 "Ks. KOWALCZYK", "GUIDE NOWAK", "O'Brien", "Van Der Berg"]
    for ok in plausible:
        assert implausible_name(ok) is None, f"false positive: {ok!r}"
    print("PASS heuristic units")


# --- (a) placeholders: held recognition primary, the guard as backstop ---
def test_park_placeholders_become_held():
    # primary: even with NO skip rule, zero Al.Mat placeholders leak into guests
    res = _park_no_skip()
    assert len(res.guests) == 23, f"expected 23 guests, got {len(res.guests)}"
    assert not [g for g in res.guests if g.cognome.strip().lower().startswith("al.mat")], \
        "an Al.Mat placeholder leaked into the guest list"
    held = [s for s in res.stays if s.status == "names_pending"]
    assert len(held) == 9 and sum(s.pax_expected for s in held) == 18

    # a COUNT-LESS placeholder has no pax to hold, so it is not held capacity —
    # disposition 3b takes it out of the guest list entirely as an
    # `unrecognized` stay. Verbatim kept, completeness blocked, no phantom.
    rows = [["h", "h"], ["names pending", ""], ["TBD", ""], ["TBA", ""]]
    cmap = ColumnMap(header_rows=1, default_role="20",
                     name_slots=[NameSlot(surname_column=0, firstname_column=1)])
    escaped = transcribe_with_stays(rows, cmap)
    assert not escaped.guests, "count-less placeholders must not become guests"
    assert all(s.status != "names_pending" for s in escaped.stays), \
        "a count-less placeholder must never become held capacity"
    unrec = [s for s in escaped.stays if s.status == "unrecognized"]
    assert sorted(s.verbatim for s in unrec) == ["TBA", "TBD", "names pending"]
    assert all(s.pax_expected == 0 for s in unrec)

    # the guard is still the backstop where it MUST be: a MIXED row carries a
    # real person, so it emits guests and the placeholder slot goes red.
    mixed = transcribe_with_stays(
        [["h", "h"], ["ROSSI", "Mario"], ["names pending", ""]],
        ColumnMap(header_rows=1, default_role="20",
                  name_slots=[NameSlot(surname_column=0, firstname_column=1)]))
    assert [g.cognome for g in mixed.guests] == ["ROSSI"]
    two_slot = transcribe_with_stays(
        [["h", "h", "h", "h"], ["ROSSI", "Mario", "names pending", ""]],
        ColumnMap(header_rows=1, default_role="20",
                  name_slots=[NameSlot(surname_column=0, firstname_column=1),
                              NameSlot(surname_column=2, firstname_column=3)]))
    assert [g.cognome for g in two_slot.guests] == ["ROSSI", "names pending"], \
        "a mixed row still emits BOTH slots — ambiguity goes to a human"
    ph = two_slot.guests[1]
    assert _name_reds(ph) and not is_submittable(ph), \
        "the placeholder slot of a mixed row must still be guard-red"
    print("PASS 9 Al.Mat rows -> held stays (map-independent); count-less "
          "placeholders -> unrecognized stays; mixed rows still guard-redded")


# --- polish 'Driver N' crew slots: caught by the FLOOR, not by the guard ---
def test_polish_drivers_become_unrecognized():
    """The open 'polish Driver' question, resolved as floor rather than
    held-pax-1: a 'Driver N' cell is an implausible label with no count, so
    disposition 3b makes it an unrecognized stay. That is strictly stronger
    than the old guard-red guest — it blocks COMPLETENESS, not just
    submission — and no phantom person reaches the guest list."""
    assert not [g for g in parse_polish()
                if g.cognome.strip().lower().startswith("driver")], \
        "no Driver row may reach the guest list"
    res = transcribe_with_stays(read_xlsx_rows(POLISH_XLSX), POLISH_MAP)
    unrec = [s for s in res.stays if s.status == "unrecognized"]
    assert sorted(s.verbatim for s in unrec) == ["Driver 1", "Driver 2"]
    assert all(s.pax_expected == 0 and s.source_row is not None for s in unrec)
    # the guard still recognizes the text — it is simply no longer the layer
    # that has to catch it
    assert all(implausible_name(s.verbatim) for s in unrec)
    print("PASS polish 'Driver N' -> 2 unrecognized stays (floor), zero "
          "phantom guests; the guard still recognizes the label")


# --- (b) categorical: real personal names clean, placeholders caught, no in-between ---
def test_no_false_positives_on_real_names():
    everyone = (list(_park_no_skip().guests) + list(parse_mix18())
                + list(parse_polish()) + list(parse_textmail()))
    real_names, false_pos, missed = 0, [], []
    for g in everyone:
        flagged = bool(_name_reds(g))
        if _is_placeholder_label(g.cognome):
            if not flagged:
                missed.append(g.cognome)
        else:
            real_names += 1
            if flagged:
                false_pos.append((g.cognome, g.nome))
    assert not false_pos, f"FALSE POSITIVES on real personal names: {false_pos}"
    # No placeholder reaches the guest list from the dev lists any more: park's
    # Al.Mat rows are held stays and polish's Driver rows are unrecognized
    # stays. So `missed` is vacuously empty here — the guard's catching duty is
    # exercised below, on the one shape that still produces a placeholder
    # GUEST: a mixed row, where a real person shares the row.
    assert not missed, f"placeholders the guard missed: {missed}"
    assert not [g for g in everyone if _is_placeholder_label(g.cognome)], \
        "no dev-list placeholder should reach the guest list at all now"

    mixed = transcribe_with_stays(
        [["h", "h", "h", "h"], ["KOVALCHUK", "IRYNA", "Driver 1", ""]],
        ColumnMap(header_rows=1, default_role="20",
                  name_slots=[NameSlot(surname_column=0, firstname_column=1),
                              NameSlot(surname_column=2, firstname_column=3)]))
    real, placeholder = mixed.guests
    assert not _name_reds(real), "the real person in a mixed row stays clean"
    assert _name_reds(placeholder) and not is_submittable(placeholder), \
        "the guard must still catch a placeholder that rides with a real name"
    print(f"PASS zero false positives across {real_names} real personal names "
          f"(mix18 + polish + park + textmail); no placeholder reaches the "
          f"guest list, and the guard still catches one riding a mixed row")


if __name__ == "__main__":
    test_heuristic_units()
    test_park_placeholders_become_held()
    test_polish_drivers_become_unrecognized()
    test_no_false_positives_on_real_names()
    print("ALL GREEN")
