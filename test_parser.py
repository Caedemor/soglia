"""
Tests for the generalized stage-2 parser. No pytest:
    python3 test_parser.py
"""
from parse_mix18 import parse as parse_hardcoded   # the original bespoke parser
from maps import parse_mix18 as parse_via_map       # MIX18 as a map + generic transcriber
from parser import transcribe, ColumnMap, FieldRule, NameSlot
from orchestrator import process_list


def main():
    # 1) the map-driven path reproduces the hardcoded MIX18 output exactly
    a = [p.guest for p in parse_hardcoded()]
    b = parse_via_map()
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

    # 4) combined-name + single-digit date + empty slot skipped
    combo = transcribe(
        [["x"], ["ROSSI Marco", "3.3.1985"], ["", ""]],
        ColumnMap(header_rows=1, default_role="16",
                  name_slots=[NameSlot(combined_column=0, name_order="surname_first")],
                  fields={"data_nascita": FieldRule(column=1, normalizer="dotted_date")}),
    )
    assert len(combo) == 1 and combo[0].cognome == "ROSSI" and combo[0].data_nascita == "03/03/1985"

    print("\u2713 PASS \u2014 generalized parser is faithful and now handles real-list variety.")
    print("        MIX18-as-a-map == hardcoded (39/39); two-people-per-row -> two guests;")
    print("        separate & combined names; blank slots skipped; dates normalized.")


if __name__ == "__main__":
    main()
