"""
All FOUR real lists through the SAME engine — proof the generalization holds,
and an honest readout of what each list does and doesn't carry.
    python3 run_lists.py
"""
from collections import Counter

from maps import (parse_mix18, parse_polish, parse_park, parse_textmail,
                  read_docx_rows, read_xlsx_rows, read_text_rows,
                  MIX18_DOCX, POLISH_XLSX, PARK_XLSX, TEXTMAIL_TXT)
from orchestrator import process_list
from validate import validate_guest

CANON = ["sesso", "data_nascita", "stato_nascita", "cittadinanza",
         "numero_documento"]


def summarize(label, raw_rows, parser):
    res = process_list(parser)
    guests = [g.guest for g in res.guests]
    n = len(guests)
    print(f"\n{'='*72}\n{label}")
    print(f"  raw rows: {len(raw_rows)}   ->   guests: {n}")
    for g in guests[:3]:
        print(f"     {g.cognome:<14} {g.nome:<16} "
              f"DOB {g.data_nascita or '—':<10} doc {g.numero_documento or '—'}")
    cov = {f: sum(1 for g in guests if getattr(g, f).strip()) for f in CANON}
    print("  coverage:", "  ".join(f"{f}={cov[f]}/{n}" for f in CANON))
    reds = Counter()
    for g in guests:
        for i in validate_guest(g):
            if i.tier == "red":
                reds[i.field] += 1
    systemic = sorted(f for f, c in reds.items() if c == n)
    print(f"  every-guest gaps: {', '.join(systemic) or 'none'}")
    return n


def main():
    a = summarize("MIX18 — Ukrainian docx (combined name; has passports)",
                  read_docx_rows(MIX18_DOCX), parse_mix18)
    b = summarize("POLISH — xlsx (separate name cols; has DOB; merged rooms; blank row)",
                  read_xlsx_rows(POLISH_XLSX), parse_polish)
    c = summarize("PARK HOTEL — xlsx (TWO people per row; names only; held rows → stays)",
                  read_xlsx_rows(PARK_XLSX), parse_park)
    d = summarize("TEXT-MAIL — strict-TSV email paste (no header; held trailer '+ 2 autisti')",
                  read_text_rows(TEXTMAIL_TXT), parse_textmail)

    print(f"\n{'='*72}\nFour very different real lists, one engine: "
          f"{a} + {b} + {c} + {d} guests parsed.")
    print("Stage-2 handled: combined/separate names, 2-per-row, blank + held rows, merged")
    print("cells, Excel date/number types, email-body TSV. Left for stage 1 / review:")
    print("embedded name markers (\"GUIDE NOWAK\", \"Ks. ...\"), proper role/party")
    print("assignment, and the missing identity fields each list simply doesn't carry.")


if __name__ == "__main__":
    main()
