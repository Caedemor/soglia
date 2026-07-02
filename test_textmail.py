"""
Tests for text ingestion (read_text_rows) + the text-mail TSV list's map.
No pytest:
    python3 test_textmail.py

The list: a real agency pastes the rooming list into an email BODY — strict
TSV, no header, 47 named lines (No. / surname / first name / DOB / doc number)
plus one tab-less trailer "+ 2 autisti" (2 unnamed drivers). Dev list only;
holdout sealed.

Also proves the dispatch floor end-to-end on the trailer —
test_trailer_is_held is the commit-1.5 FLIP of the previously pinned known
gap (the pin working as designed: the fix was forced through the assertions).
"""
import os

from maps import read_text_rows, parse_textmail, TEXTMAIL_TXT, TEXTMAIL_MAP
from parser import transcribe_report, transcribe_with_stays
from stay import held_pax, reconcile, completeness_status

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


# --- the trailer: held capacity via the residue path --------------------------
def test_trailer_is_held():
    """The commit-1.5 FLIP of the pinned gap: the '+ 2 autisti' trailer is a
    held Stay via the RESIDUE path — no slot structure, so the text's N is
    AUTHORITATIVE (pax_expected=2; slot capacity would wrongly say 1). Before
    the dispatch floor this row vanished entirely and the list read a FALSE
    "complete" (47/47/0); the transition is asserted below, explicitly."""
    rows = read_text_rows(TEXTMAIL_TXT)
    res = transcribe_with_stays(rows, TEXTMAIL_MAP)

    assert held_pax("+ 2 autisti") == 2               # vocabulary now spoken
    assert len(res.guests) == 47 and not any(
        "autisti" in (g.cognome + g.nome) for g in res.guests), \
        "trailer must never leak into guests"
    held = [s for s in res.stays if s.status == "names_pending"]
    assert len(held) == 1, "the trailer is exactly one held stay"
    t = held[0]
    assert (t.pax_expected, t.verbatim, t.source_row) == (2, "+ 2 autisti", 47)
    assert len(res.stays) == 48, "47 named stays + the held trailer"
    assert not [s for s in res.stays if s.status == "unrecognized"]
    assert all(g.stay_id != t.stay_id for g in res.guests), \
        "no guest may sit on the held trailer"

    # the false-complete is dead: 47/47/0 "complete" -> 49/47/2 awaiting
    rec = reconcile(res.stays, res.guests)
    assert rec == {"expected": 49, "named": 47, "pending": 2,
                   "overage": 0, "unrecognized": 0}, rec
    assert completeness_status(rec) == "awaiting_completion", \
        "two unnamed drivers must keep the list from reading complete"

    rep = transcribe_report(rows, TEXTMAIL_MAP)
    assert (rep.guests, rep.held_stays, rep.held_pax,
            rep.unrecognized_rows) == (47, 1, 2, 0)
    assert "held capacity" in rep.summary()
    print("PASS trailer '+ 2 autisti' -> held stay pax 2 (residue path, text-N "
          "authoritative); false complete 47/47/0 -> 49/47/2 awaiting_completion")


if __name__ == "__main__":
    test_reader_contract()
    test_textmail_guests()
    test_trailer_is_held()
    print("ALL GREEN")
