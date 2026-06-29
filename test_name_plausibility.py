"""
Tests for the deterministic name-plausibility guard in validate.py.

Both directions matter equally:
  (a) the 9 held "Al.Mat. arrivi N pax" placeholder rows in the Park list each
      raise a RED name issue and are non-submittable — the silent-miss that
      stage 1 could not catch (those rows fall outside its sample window) is now
      caught downstream, deterministically, on EVERY row;
  (b) NOT ONE real PERSONAL NAME across the three dev samples is falsely
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
from parser import transcribe
from maps import (parse_mix18, parse_polish, parse_park,
                  read_xlsx_rows, PARK_XLSX, PARK_MAP)


def _park_guests_no_skip():
    """Transcribe the Park list WITHOUT the hand-written skip rule — i.e. exactly
    what the live model's map produced (it never inferred the held-row skip).
    This is the 32-guest output the deterministic guard has to police: 23 real
    crew + 9 held 'Al.Mat. arrivi N pax' placeholders."""
    no_skip = dataclasses.replace(PARK_MAP, skip_row=None)
    return transcribe(read_xlsx_rows(PARK_XLSX), no_skip)


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


# --- (a) every Al.Mat placeholder row is caught RED and held back ---
def test_park_placeholders_flagged():
    placeholders = [g for g in _park_guests_no_skip()
                    if g.cognome.strip().lower().startswith("al.mat")]
    assert len(placeholders) == 9, f"expected 9 held rows, got {len(placeholders)}"
    for i, g in enumerate(placeholders):
        assert _name_reds(g), f"Al.Mat row {i} ({g.cognome!r}) not flagged as a name issue"
        assert not is_submittable(g), f"Al.Mat row {i} should be non-submittable"
    print(f"PASS {len(placeholders)} Al.Mat rows flagged RED + non-submittable")


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
    everyone = list(_park_guests_no_skip()) + list(parse_mix18()) + list(parse_polish())
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
    assert not missed, f"placeholders the guard missed: {missed}"
    print(f"PASS zero false positives across {real_names} real personal names "
          f"(mix18 + polish + park), all placeholders caught")


if __name__ == "__main__":
    test_heuristic_units()
    test_park_placeholders_flagged()
    test_polish_driver_placeholders_flagged()
    test_no_false_positives_on_real_names()
    print("ALL GREEN")
