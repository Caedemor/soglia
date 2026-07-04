"""
Tests for the deterministic name-plausibility guard in validate.py.

Both directions matter equally:
  (a) the 9 held "Al.Mat. arrivi N pax" placeholder rows in the Park list are
      now caught UPSTREAM of the guard by held-capacity recognition (stay.py)
      — deterministically, on EVERY row, regardless of the map's skip rule
      (stage 1's sample window never saw them). They become names_pending
      stays, never guests. The guard remains the BACKSTOP: a placeholder that
      escapes held recognition (e.g. count-less "names pending") is still
      emitted as a guest and RED-flagged, non-submittable;
  (b) NOT ONE real PERSONAL NAME across the four dev samples is falsely
      flagged. The guard must not cry wolf on real names — Cyrillic, Polish
      diacritics, compound given names, the honorific "Ks. KOWALCZYK", or the
      role marker "GUIDE NOWAK" are all valid and must pass.

Note: the guard also catches a SECOND placeholder pattern we did not design for
— the Polish list carries two "Driver N" crew slots (a digit where a name
belongs). These are not real personal names; flagging them RED is correct, and
demonstrates the guard generalizing by category rather than matching "Al.Mat".

Dev samples only (maps.py). The holdout set is never read here.
"""
import dataclasses

from validate import _implausible_name, validate_guest, is_submittable
from parser import transcribe, transcribe_with_stays, ColumnMap, NameSlot
from maps import (parse_mix18, parse_polish, parse_textmail, parse_park,
                  read_xlsx_rows, PARK_XLSX, PARK_MAP)


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
        assert _implausible_name(bad) is not None, f"should flag: {bad!r}"

    # unusual-but-real names must pass untouched (no specific string is hardcoded)
    plausible = ["KOVALCHUK", "Ткаченко", "Ірина", "WÓJCIK", "Wiśniewski",
                 "Dąbrowski", "Zając", "Sikora", "Tomasz Grzegorz",
                 "Ks. KOWALCZYK", "GUIDE NOWAK", "O'Brien", "Van Der Berg"]
    for ok in plausible:
        assert _implausible_name(ok) is None, f"false positive: {ok!r}"
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

    # backstop: a COUNT-LESS placeholder escapes held recognition (no pax to
    # count -> deliberately not held) and must land as a guard-red guest.
    rows = [["h", "h"], ["names pending", ""], ["TBD", ""]]
    cmap = ColumnMap(header_rows=1, default_role="20",
                     name_slots=[NameSlot(surname_column=0, firstname_column=1)])
    escaped = transcribe_with_stays(rows, cmap)
    assert len(escaped.guests) == 2, "count-less placeholders must be emitted, not held"
    assert all(s.status != "names_pending" for s in escaped.stays), \
        "a count-less placeholder must never become held capacity"
    for g in escaped.guests:
        assert _name_reds(g) and not is_submittable(g), \
            f"escaped placeholder {g.cognome!r} not guard-flagged"
    print("PASS 9 Al.Mat rows -> held stays (map-independent); "
          "count-less placeholders guard-flagged as backstop")


# --- the guard generalizes: polish 'Driver N' crew slots are caught too ---
def test_polish_driver_placeholders_flagged():
    drivers = [g for g in parse_polish()
               if g.cognome.strip().lower().startswith("driver")]
    assert len(drivers) == 2, f"expected 2 Driver rows in polish, got {len(drivers)}"
    for g in drivers:
        assert _name_reds(g), f"{g.cognome!r} not flagged as a name issue"
        assert not is_submittable(g), f"{g.cognome!r} should be non-submittable"
    print(f"PASS {len(drivers)} polish 'Driver N' placeholders flagged RED + non-submittable")


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
    # the only placeholders left AMONG GUESTS are polish's Driver rows (park's
    # Al.Mat rows are held stays now and never reach the guest list at all)
    assert not missed, f"placeholders the guard missed: {missed}"
    print(f"PASS zero false positives across {real_names} real personal names "
          f"(mix18 + polish + park + textmail), all placeholders caught")


if __name__ == "__main__":
    test_heuristic_units()
    test_park_placeholders_become_held()
    test_polish_driver_placeholders_flagged()
    test_no_false_positives_on_real_names()
    print("ALL GREEN")
