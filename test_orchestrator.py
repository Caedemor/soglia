"""
Tests for the orchestrator. No pytest:
    python3 test_orchestrator.py
"""
from parse_mix18 import parse
from orchestrator import process_list
from tracciato import Guest

UA = "100000999"


def fake_parser():
    """A different 'parser' — two already-complete guests — to prove swappability."""
    return [
        Guest(tipo_alloggiato="16", cognome="ROSSI", nome="MARCO", sesso="1",
              data_nascita="08/11/1990", stato_nascita="100000100",
              cittadinanza="100000100", born_in_italy=True,
              comune_nascita="015146", provincia_nascita="MI",
              tipo_documento="IDENT", numero_documento="CA1", luogo_rilascio="015146"),
        Guest(tipo_alloggiato="16", cognome="BIANCHI", nome="SARA", sesso="2",
              data_nascita="03/03/1985", stato_nascita="100000100",
              cittadinanza="100000100", born_in_italy=True,
              comune_nascita="015146", provincia_nascita="MI",
              tipo_documento="IDENT", numero_documento="CA2", luogo_rilascio="015146"),
    ]


def main():
    # 1) the SAME orchestrator runs a totally different parser, no changes
    clean = process_list(fake_parser)
    assert clean.total == 2
    assert len(clean.submittable) == 2, "two complete guests should be submittable"
    lines = clean.tracciato(data_arrivo="12/06/2026", giorni_permanenza=2).split("\r\n")
    assert len(lines) == 2 and all(len(x) == 168 for x in lines), "should format 2 valid lines"

    # 2) the real MIX18 list through the same entry point
    res = process_list(parse, infer_country_code=UA, infer_country_name="Ukraine")
    assert res.total == 39
    recon = res.reconciliation()
    assert recon == {"total": 39, "submittable": len(res.submittable),
                     "blocked": len(res.blocked)}
    # suggestions are attached but NOT auto-applied -> reds remain -> nothing submittable yet
    assert len(res.submittable) == 0, "orchestrator must not auto-accept suggestions"
    assert all(len(g.suggestions) > 0 for g in res.guests), "every guest got suggestions"

    # 3) the blocked guests carry their reasons; meta carries parser context
    leader = next(g for g in res.guests if g.guest.cognome == "Ткаченко")
    assert {"tipo_documento", "numero_documento", "luogo_rilascio"} <= {i.field for i in leader.reds}
    assert leader.meta.get("room") == "SGL 1", "parser context flows through meta"

    print("\u2713 PASS \u2014 orchestrator composes the pipeline into one result.")
    print("        same entry point ran a fake parser AND the real MIX18 list;")
    print("        result object reports reconciliation, per-guest reds, suggestions, and bytes;")
    print("        suggestions stay advisory (not auto-applied); parser context flows via meta.")


if __name__ == "__main__":
    main()
