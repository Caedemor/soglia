"""
Tests for the generalized stage-2 parser. No pytest:
    python3 test_parser.py
"""
import dataclasses

from parse_mix18 import parse as parse_hardcoded   # the original bespoke parser
from maps import parse_mix18 as parse_via_map       # MIX18 as a map + generic transcriber
from parser import transcribe, ColumnMap, FieldRule, NameSlot
from orchestrator import process_list


def main():
    # 1) the map-driven path reproduces the hardcoded MIX18 output exactly.
    # stay_id is normalized out: the bespoke parser predates stays (None), the
    # map path links every guest to its row's Stay — IDENTITY must be equal.
    a = [p.guest for p in parse_hardcoded()]
    b = [dataclasses.replace(g, stay_id=None) for g in parse_via_map()]
    assert len(a) == len(b) == 39, f"expected 39 each, got {len(a)} and {len(b)}"
    for i, (x, y) in enumerate(zip(a, b)):
        assert x == y, f"row {i} differs:\n  hardcoded = {x}\n  via_map   = {y}"

    # 2) plugs into the same orchestrator
    assert process_list(parse_via_map).total == 39

    # 3) TWO people per row -> two guests (the Park Hotel shape)
    twin_rows = [
        ["h"],                                              # header
        ["GIORDANO", "Davide", "MANCINI", "Salvatore"],     # one row, two people
        ["ROSSI", "Alessandro", "", ""],                    # one row, one person
    ]
    twin_map = ColumnMap(
        header_rows=1, default_role="20",
        name_slots=[NameSlot(surname_column=0, firstname_column=1),
                    NameSlot(surname_column=2, firstname_column=3)],
    )
    g = transcribe(twin_rows, twin_map)
    assert len(g) == 3, f"expected 3 guests from 2 rows, got {len(g)}"
    assert (g[0].cognome, g[1].cognome, g[2].cognome) == ("GIORDANO", "MANCINI", "ROSSI")
    # a twin is ONE stay carrying two guests; the next row is a different stay
    assert g[0].stay_id == g[1].stay_id and g[1].stay_id != g[2].stay_id

    # 4) combined-name + single-digit date + empty slot skipped
    combo = transcribe(
        [["x"], ["ROSSI Marco", "3.3.1985"], ["", ""]],
        ColumnMap(header_rows=1, default_role="16",
                  name_slots=[NameSlot(combined_column=0, name_order="surname_first")],
                  fields={"data_nascita": FieldRule(column=1, normalizer="dotted_date")}),
    )
    assert len(combo) == 1 and combo[0].cognome == "ROSSI" and combo[0].data_nascita == "03/03/1985"

    # 4) warm-up fixes (commit 3 cycle): never invent a century; never crash
    # on a short row. No dev-list data has 2-digit years, so behavior on the
    # real samples is byte-identical — these pin the edges.
    from parser import norm_dotted_date
    assert norm_dotted_date("03.03.1985") == "03/03/1985"
    assert norm_dotted_date("3.3.85") == "3.3.85", \
        "2-digit year stays VERBATIM (ambiguous DOB) — the validator reds it"
    from validate import validate_guest, is_submittable
    g85 = dataclasses.replace(parse_via_map()[0], data_nascita=norm_dotted_date("3.3.85"))
    assert any(i.field == "data_nascita" for i in validate_guest(g85)) \
        and not is_submittable(g85), "verbatim 2-digit date must land RED"
    from maps import MIX18_MAP
    short_row = ["1", "ROSSI Mario", "", "", "03.03.1985", "AB123456"]  # no col 7
    got = transcribe(  [["h"]*8, short_row], MIX18_MAP)
    assert len(got) == 1 and got[0].tipo_alloggiato == "20", \
        "a short row takes the default role, never an IndexError"

    print("\u2713 PASS \u2014 generalized parser is faithful and now handles real-list variety.")
    print("        MIX18-as-a-map == hardcoded (39/39); two-people-per-row -> two guests;")
    print("        separate & combined names; blank slots skipped; dates normalized.")


if __name__ == "__main__":
    main()
