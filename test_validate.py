"""
Known-answer tests for the validator. No pytest:
    python3 test_validate.py

Each case has a hand-decided expected outcome: which fields should go red, and
which guests should come back clean. The tour leader is the real one from the
Ukrainian list — a single guest with a birth date but no passport.
"""
from datetime import date
from tracciato import Guest
from validate import validate_guest, is_submittable

UKR, ITA, MILANO, PASS = "100000999", "100000100", "015146", "PASOR"
TODAY = date(2026, 6, 12)   # fixed so plausibility checks don't depend on the clock


def red_fields(g):
    return {i.field for i in validate_guest(g, today=TODAY) if i.tier == "red"}


# --- clean guests: should produce NO red issues -----------------------------
CLEAN = {
    "capo famiglia (UA, passport)": Guest(
        tipo_alloggiato="17", cognome="KOVALCHUK", nome="IRYNA", sesso="2",
        data_nascita="23/02/1958", stato_nascita=UKR, cittadinanza=UKR,
        born_in_italy=False, tipo_documento=PASS, numero_documento="FZ180350",
        luogo_rilascio=UKR),
    "familiare (UA, no doc needed)": Guest(
        tipo_alloggiato="19", cognome="KOVALCHUK", nome="ARTEM", sesso="1",
        data_nascita="17/09/2014", stato_nascita=UKR, cittadinanza=UKR,
        born_in_italy=False),
    "ospite singolo (IT, born Milano)": Guest(
        tipo_alloggiato="16", cognome="ROSSI", nome="MARCO", sesso="1",
        data_nascita="08/11/1990", stato_nascita=ITA, cittadinanza=ITA,
        born_in_italy=True, comune_nascita=MILANO, provincia_nascita="MI",
        tipo_documento="IDENT", numero_documento="CA12345AB", luogo_rilascio=MILANO),
}

# --- problem guests: field -> must be among the red fields ------------------
# The TOUR LEADER, straight from the Ukrainian list: single guest, has a birth
# date, but NO passport. A single occupant is a head, so a document is required.
TOUR_LEADER = Guest(
    tipo_alloggiato="16", cognome="TKACHENKO", nome="IRYNA", sesso="2",
    data_nascita="05/12/1984", stato_nascita=UKR, cittadinanza=UKR,
    born_in_italy=False)   # no tipo_documento / numero / luogo

PROBLEM_CASES = [
    ("tour leader: missing document", TOUR_LEADER,
     {"tipo_documento", "numero_documento", "luogo_rilascio"}),
    ("impossible birth date (30 Feb)",
     Guest(tipo_alloggiato="16", cognome="BIANCHI", nome="LUCA", sesso="1",
           data_nascita="30/02/1992", stato_nascita=ITA, cittadinanza=ITA,
           born_in_italy=True, comune_nascita=MILANO, provincia_nascita="MI",
           tipo_documento="IDENT", numero_documento="X1", luogo_rilascio=MILANO),
     {"data_nascita"}),
    ("birth date in the future",
     Guest(tipo_alloggiato="16", cognome="VERDI", nome="SARA", sesso="2",
           data_nascita="01/01/2099", stato_nascita=ITA, cittadinanza=ITA,
           born_in_italy=True, comune_nascita=MILANO, provincia_nascita="MI",
           tipo_documento="IDENT", numero_documento="X1", luogo_rilascio=MILANO),
     {"data_nascita"}),
    ("born in Italy but no comune/provincia",
     Guest(tipo_alloggiato="19", cognome="NERI", nome="GIO", sesso="1",
           data_nascita="03/03/1980", stato_nascita=ITA, cittadinanza=ITA,
           born_in_italy=True),
     {"comune_nascita", "provincia_nascita"}),
    ("surname too long",
     Guest(tipo_alloggiato="19", cognome="A" * 51, nome="GIO", sesso="1",
           data_nascita="03/03/1980", stato_nascita=UKR, cittadinanza=UKR,
           born_in_italy=False),
     {"cognome"}),
    ("bad sesso value",
     Guest(tipo_alloggiato="19", cognome="GALLO", nome="EVA", sesso="X",
           data_nascita="03/03/1980", stato_nascita=UKR, cittadinanza=UKR,
           born_in_italy=False),
     {"sesso"}),
]


def main():
    # clean guests
    for label, g in CLEAN.items():
        rf = red_fields(g)
        assert rf == set(), f"expected CLEAN, got red {rf} for: {label}"
        assert is_submittable(g, today=TODAY), f"should be submittable: {label}"

    # problem guests — required red field(s) must be present
    for label, g, must_be_red in PROBLEM_CASES:
        rf = red_fields(g)
        missing = must_be_red - rf
        assert not missing, f"{label}: expected red on {must_be_red}, missing {missing} (got {rf})"
        assert not is_submittable(g, today=TODAY), f"should NOT be submittable: {label}"

    print("\u2713 PASS \u2014 validator behaves on every known case.")
    print(f"        {len(CLEAN)} clean guests flagged nothing; "
          f"{len(PROBLEM_CASES)} problem guests flagged correctly.\n")
    print("Tour leader (single guest, no passport) \u2014 issues raised:")
    for i in validate_guest(TOUR_LEADER, today=TODAY):
        print(f"  {i}")


if __name__ == "__main__":
    main()
