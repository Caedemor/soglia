"""
The full pipeline with stage 1 in front, on all three real lists:
    python3 run_llm.py

  raw file --[stage 1: model -> ColumnMap]--> [stage 2: transcribe] --> orchestrator

Here stage 1 is replayed from a saved model answer (offline). In production you
pass a live caller instead — the ONLY line that changes is which caller goes in.
"""
from maps import (read_docx_rows, read_xlsx_rows, MIX18_DOCX, POLISH_XLSX, PARK_XLSX)
from llm_parser import infer_map, replay_caller
from parser import transcribe
from orchestrator import process_list

CASES = [
    ("MIX18 — Ukrainian docx",   read_docx_rows, MIX18_DOCX,  "llm_maps/mix18.json"),
    ("POLISH — pilgrimage xlsx",  read_xlsx_rows, POLISH_XLSX, "llm_maps/polish.json"),
    ("PARK HOTEL — crew xlsx",    read_xlsx_rows, PARK_XLSX,   "llm_maps/park.json"),
]


def main():
    for label, reader, path, fixture in CASES:
        rows = reader(path)
        # PRODUCTION: infer_map(rows, anthropic_caller)  or  infer_map(rows, my_local_caller)
        cmap, notes = infer_map(rows, replay_caller(fixture))
        guests = transcribe(rows, cmap)
        res = process_list(lambda g=guests: g)
        print(f"\n{'='*70}\n{label}")
        print(f"  stage 1 produced a map -> stage 2 transcribed {res.total} guests "
              f"(parser never changed).")
        print("  what the model flagged for review:")
        for n in notes:
            print(f"    \u2022 {n}")

    print(f"\n{'='*70}")
    print("Same engine, three layouts, zero per-list Python — the model produced each map.")
    print("Data-residency decision = which caller you inject. Today: replay (offline).")
    print("Tomorrow: anthropic_caller (your key) or a local model — nothing else moves.")


if __name__ == "__main__":
    main()
