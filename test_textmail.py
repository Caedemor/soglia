"""
Tests for text ingestion (read_text_rows) + the text-mail TSV list's map.
No pytest:
    python3 test_textmail.py

The list: a real agency pastes the rooming list into an email BODY — strict
TSV, no header, 47 named lines (No. / surname / first name / DOB / doc number)
plus one tab-less trailer "+ 2 autisti" (2 unnamed drivers). Dev list only;
holdout sealed.

Also pins, EXPLICITLY, the current (known-gap) disposition of the trailer —
see test_trailer_known_gap. Do not "fix" that here; the held-recognition
generalisation is the next commit.
"""
import os

from maps import read_text_rows, parse_textmail, TEXTMAIL_TXT, TEXTMAIL_MAP
from parser import transcribe_with_stays
from stay import held_pax

TMP = "/tmp/soglia_test_textmail.txt"


# --- the reader: strict TSV, narrow hygiene ----------------------------------
def test_reader_contract():
    rows = read_text_rows(TEXTMAIL_TXT)
    assert len(rows) == 48, f"expected 48 rows, got {len(rows)}"
    assert all(len(r) == 5 for r in rows[:47]), "named lines must split into 5 fields"
    assert rows[47] == ["+ 2 autisti"], f"trailer must survive as a 1-cell row: {rows[47]}"

    # hygiene, narrowly: BOM stripped, trailing blanks dropped, interior blank KEPT
    with open(TMP, "w", encoding="utf-8") as f:
        f.write("﻿1\tA\tB\tc\td\n\n2\tE\tF\tg\th\n\n \n")
    try:
        rows = read_text_rows(TMP)
        assert rows[0][0] == "1", f"BOM must be stripped: {rows[0][0]!r}"
        assert len(rows) == 3, f"trailing blank lines must be dropped: {len(rows)} rows"
        assert rows[1] == [""], "an INTERIOR blank line stays as an empty row (structural)"
    finally:
        os.remove(TMP)
    print("PASS reader: 48 rows (47x5 + 1-cell trailer); BOM/trailing stripped, interior blank kept")


# --- the map: 47 named guests, fields verbatim -------------------------------
def test_textmail_guests():
    guests = parse_textmail()
    assert len(guests) == 47, f"expected 47 named guests, got {len(guests)}"

    g1 = guests[0]
    assert (g1.cognome, g1.nome) == ("Klimowicz", "Ks. Tomasz"), \
        "the 'Ks.' honorific rides VERBATIM in the first name (stage-1/review strips, not us)"
    assert g1.data_nascita == "14/07/1992" and g1.numero_documento == "KPT 837261"
    assert g1.tipo_documento == "PASOR", "doc type = passport when a number is present"

    g26 = guests[25]     # diacritics must survive the text reader
    assert (g26.cognome, g26.nome) == ("Maślaniec", "Lidia")
    assert g26.data_nascita == "21/10/1977" and g26.numero_documento == "PBD 601843"

    # line 47: missing doc number -> guest still parsed, doc fields EMPTY (null is valid)
    g47 = guests[46]
    assert (g47.cognome, g47.nome) == ("Hejnar", "Danuta")
    assert g47.data_nascita == "30/07/1962"
    assert g47.numero_documento == "" and g47.tipo_documento == "", \
        "a missing doc number stays empty — never guessed, never a dropped row"

    import re
    assert all(re.fullmatch(r"\d{2}/\d{2}/\d{4}", g.data_nascita) for g in guests), \
        "every DOB normalizes to dd/mm/yyyy"
    assert all(g.tipo_alloggiato == "20" for g in guests)   # role assignment = stage-1/review territory
    print("PASS 47 named guests; verbatim honorific; missing doc number -> empty, not dropped")


# --- the trailer: KNOWN GAP, pinned deliberately ------------------------------
def test_trailer_known_gap():
    """KNOWN GAP (do not 'fix' here — held-recognition generalisation is the
    next commit, on a branch): the '+ 2 autisti' trailer is HELD capacity
    (2 unnamed drivers), but today it yields NOTHING — no guest, no stay, no
    red. Two independent misses compound:
      1. its only cell sits in column 0, OUTSIDE the map's name slots, so the
         four-way dispatch reads the row as a genuine blank (it never even
         reaches the guard as a pseudo-guest);
      2. even if it did reach the recognizer, held_pax() speaks only 'pax' —
         '2 autisti' is a count in a vocabulary it doesn't know.
    The next commit must reclassify it as a held Stay with pax_expected=2 and
    the cell text verbatim (§8.5.7: nothing vanishes unreviewably). When it
    does, THESE ASSERTIONS MUST FLIP — that is the point of pinning them."""
    rows = read_text_rows(TEXTMAIL_TXT)
    res = transcribe_with_stays(rows, TEXTMAIL_MAP)

    assert held_pax("+ 2 autisti") is None            # miss 2: vocabulary
    assert len(res.guests) == 47 and not any(
        "autisti" in (g.cognome + g.nome) for g in res.guests), \
        "trailer must not leak into guests as long as the gap stands"
    held = [s for s in res.stays if s.status == "names_pending"]
    assert held == [], "trailer is NOT yet a held stay (that is the gap)"
    assert len(res.stays) == 47, "one named stay per guest line, none for the trailer"
    print("PASS (known gap pinned) trailer '+ 2 autisti' currently vanishes: "
          "no guest, no stay, no red — next commit turns it into held pax_expected=2")


if __name__ == "__main__":
    test_reader_contract()
    test_textmail_guests()
    test_trailer_known_gap()
    print("ALL GREEN")
