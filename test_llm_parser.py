"""
Tests for the stage-1 LLM plug. No pytest:
    python3 test_llm_parser.py

The proof: a map PRODUCED by the model (replayed from a saved answer) must run
through the existing stage-2 transcriber and yield byte-identical guests to the
hand-tuned maps. If so, the model's output is correct and the plug is faithful.
"""
from maps import (read_docx_rows, read_xlsx_rows, MIX18_DOCX, POLISH_XLSX, PARK_XLSX,
                  parse_mix18, parse_polish, parse_park)
from llm_parser import infer_map, parse_map_json, replay_caller, anthropic_caller
from parser import transcribe

# Counts reflect NON-DESTRUCTIVE skips plus HELD-CAPACITY recognition: a skip
# rule flags rows instead of deleting them, so polish also emits its 7 header/
# legend rows (48 guests + 7). Park's 9 held "Al.Mat" rows are recognized as
# held capacity in code (stay.py) BEFORE the map's skip rule — they become
# names_pending stays, never guests, so park yields its 23 real crew. mix18 has
# neither, so it is unchanged. Parity still holds exactly: both the model map
# and the hand map run the SAME transcriber, held recognition included.
CASES = [
    ("MIX18",  read_docx_rows, MIX18_DOCX, "llm_maps/mix18.json",  parse_mix18, 39),
    ("POLISH", read_xlsx_rows, POLISH_XLSX, "llm_maps/polish.json", parse_polish, 55),
    ("PARK",   read_xlsx_rows, PARK_XLSX,   "llm_maps/park.json",   parse_park,   23),
]


def main():
    # 1) each model-produced map reproduces the hand-tuned guests EXACTLY
    for label, reader, path, fixture, hand_fn, expected in CASES:
        rows = reader(path)
        cmap, notes = infer_map(rows, replay_caller(fixture))
        via_llm = transcribe(rows, cmap)
        via_hand = hand_fn()
        assert len(via_llm) == expected, f"{label}: expected {expected}, got {len(via_llm)}"
        assert via_llm == via_hand, f"{label}: model-map guests differ from hand-map guests"
        assert notes, f"{label}: model should surface review notes"

    # 2) the compiler validates the model's answer (a mistake can't slip through)
    for bad in ['{"fields": {"not_a_field": {"column": 0}}}',
                '{"fields": {"sesso": {"column": 0, "normalizer": "make_up_data"}}}']:
        try:
            parse_map_json(bad); raise AssertionError("should have rejected an invalid map")
        except ValueError:
            pass

    # 3) tolerate fenced / chatty output around the JSON
    fenced = '```json\n{"header_rows":1,"name_slots":[{"combined_column":0}],"fields":{}}\n```'
    cmap, _ = parse_map_json(fenced)
    assert cmap.header_rows == 1 and len(cmap.name_slots) == 1

    # 4) the swap-in story is concrete: the real caller fails loudly without a key
    try:
        anthropic_caller("hi"); raise AssertionError("should require a key")
    except RuntimeError as e:
        assert "data-residency" in str(e)

    print("\u2713 PASS \u2014 stage-1 LLM plug is faithful and safe.")
    print("        model-produced maps reproduce the hand-tuned guests exactly on all 3 lists;")
    print("        the compiler rejects invalid fields/normalizers; fenced output tolerated;")
    print("        the model is swappable and the real caller defers to your data-residency choice.")


if __name__ == "__main__":
    main()
