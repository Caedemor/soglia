"""
Golden-file test for the tracciato formatter.

No pytest needed — just run:
    python3 build_golden.py     # (re)write the authoritative answer
    python3 test_tracciato.py   # check the formatter reproduces it

What this proves: given clean, post-review canonical guests, the formatter emits
the exact bytes the Alloggiati portal expects (per our §4.2 reading). It also
guards the member-document rule and the no-trailing-newline rule.
"""
import os
from tracciato import Guest, format_schedina, format_tracciato, FIELD_SPEC

# Same placeholder codes as the golden file.
UKR = "100000999"
PASS = "PASOR"
ITA = "100000100"
MILANO = "015146"

# Post-review canonical fixture — the KOVALCHUK family (TWIN 1) + one Italian single.
FIXTURE = [
    Guest(tipo_alloggiato="17", cognome="KOVALCHUK", nome="IRYNA", sesso="2",
          data_nascita="23/02/1958", stato_nascita=UKR, cittadinanza=UKR,
          born_in_italy=False,
          tipo_documento=PASS, numero_documento="FZ180350", luogo_rilascio=UKR),
    # Member: we deliberately pass a passport (GU900515). The formatter must DROP it,
    # leaving the document fields blank.
    Guest(tipo_alloggiato="19", cognome="KOVALCHUK", nome="ARTEM", sesso="1",
          data_nascita="17/09/2014", stato_nascita=UKR, cittadinanza=UKR,
          born_in_italy=False,
          tipo_documento=PASS, numero_documento="GU900515", luogo_rilascio=UKR),
    # Born in Italy: comune + provincia must be FILLED (the other birth branch).
    Guest(tipo_alloggiato="16", cognome="ROSSI", nome="MARCO", sesso="1",
          data_nascita="08/11/1990", stato_nascita=ITA, cittadinanza=ITA,
          born_in_italy=True, comune_nascita=MILANO, provincia_nascita="MI",
          tipo_documento="IDENT", numero_documento="CA12345AB", luogo_rilascio=MILANO),
]


def load_golden():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden", "family_twin.txt")
    with open(path, "r", encoding="utf-8", newline="") as f:
        return f.read()


def show(line):
    """Print a field-by-field breakdown so a human can eyeball it against §4.2."""
    i = 0
    for name, w in FIELD_SPEC:
        print(f"  [{i:>3}:{i+w:>3}] {name:<18} |{line[i:i+w]}|")
        i += w


def main():
    got = format_tracciato(FIXTURE, data_arrivo="12/06/2026", giorni_permanenza=2)
    want = load_golden()

    lines = got.split("\r\n")

    # 1) structure: three 168-char schedine, no trailing newline
    assert len(lines) == 3, f"expected 3 schedine, got {len(lines)}"
    for n, ln in enumerate(lines, 1):
        assert len(ln) == 168, f"line {n} is {len(ln)} chars, expected 168"
    assert not got.endswith("\r\n"), "file must NOT end with a trailing CR+LF"

    # 2) the member's three document fields must be blank despite a passport in input
    member = lines[1]
    assert member[134:168] == " " * 34, "familiare document fields must be blank"

    # 3) the Italian-born guest must have comune + provincia FILLED (not blank)
    assert lines[2][105:114].strip() != "", "born-in-Italy: comune nascita must be filled"
    assert lines[2][114:116].strip() != "", "born-in-Italy: provincia must be filled"

    # 3) exact match against the independently-built golden file
    if got != want:
        print("✗ MISMATCH — formatter output, field by field:\n")
        for n, ln in enumerate(lines, 1):
            print(f"line {n}:")
            show(ln)
            print()
        for k, (a, b) in enumerate(zip(got, want)):
            if a != b:
                print(f"first difference at offset {k}: got {a!r}, want {b!r}")
                break
        raise SystemExit(1)

    # 4) over-length must RAISE, never silently lose char 51 (handoff §8.2)
    too_long = Guest(tipo_alloggiato="16", cognome="A" * 51, nome="MARCO", sesso="1",
                     data_nascita="08/11/1990", stato_nascita=ITA, cittadinanza=ITA,
                     born_in_italy=True, comune_nascita=MILANO, provincia_nascita="MI",
                     tipo_documento="IDENT", numero_documento="CA12345AB", luogo_rilascio=MILANO)
    try:
        format_schedina(too_long, data_arrivo="12/06/2026", giorni_permanenza=2)
        raise SystemExit("\u2717 FAIL: 51-char surname did not raise (silent-truncation risk)")
    except ValueError:
        pass  # correct: it refused rather than corrupt a police record

    print("\u2713 PASS \u2014 all checks green.")
    print("        3 schedine, 168 chars each, CR+LF between, no trailing newline,")
    print("        member doc fields blank, born-in-Italy comune+provincia filled,")
    print("        over-length surname correctly refused (no silent truncation).\n")
    print("Line 3 (ROSSI MARCO, ospite singolo, born in Italy) \u2014 field by field:")
    show(lines[2])


if __name__ == "__main__":
    main()
