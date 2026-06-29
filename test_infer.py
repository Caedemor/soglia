"""
Known-answer tests for the inference add-on. No pytest:
    python3 test_infer.py
"""
from tracciato import Guest
from infer import suggest, apply_suggestions

UA = "100000999"   # placeholder Ukraine code


def blank(nome="IRYNA", sesso="", citt="", stato="", born_it=False):
    return Guest(tipo_alloggiato="20", cognome="X", nome=nome, sesso=sesso,
                 data_nascita="01/01/1990", stato_nascita=stato, cittadinanza=citt,
                 born_in_italy=born_it)


def fields(suggs):
    return {s.field: s.value for s in suggs}


def main():
    # name -> sex, both scripts
    assert fields(suggest(blank("IRYNA"))).get("sesso") == "2", "IRYNA -> F"
    assert fields(suggest(blank("ARTEM"))).get("sesso") == "1", "ARTEM -> M"
    assert fields(suggest(blank("Богдан"))).get("sesso") == "1", "Cyrillic Bohdan -> M"

    # unknown name -> NO sex suggestion (field stays red, correctly)
    assert "sesso" not in fields(suggest(blank("Zzqq"))), "unknown name must not suggest"

    # culturally ambiguous -> refused on purpose
    assert "sesso" not in fields(suggest(blank("Andrea"))), "ambiguous name must not suggest"

    # never overwrite a value that's already present
    assert suggest(blank("IRYNA", sesso="2")) == [], "present sesso must not be re-suggested"

    # list-level defaults only when a country hint is supplied, only for empty fields
    s = suggest(blank("IRYNA"), list_country_code=UA, list_country_name="Ukraine")
    f = fields(s)
    assert f.get("cittadinanza") == UA and f.get("stato_nascita") == UA, "list defaults proposed"
    assert suggest(blank("IRYNA")) and "cittadinanza" not in fields(suggest(blank("IRYNA"))), \
        "no country hint -> no citizenship suggestion"

    # apply produces a new, filled guest without mutating the original
    g = blank("IRYNA")
    g2 = apply_suggestions(g, suggest(g, list_country_code=UA, list_country_name="Ukraine"))
    assert g.sesso == "" and g2.sesso == "2", "apply must not mutate the original"
    assert g2.cittadinanza == UA and g2.stato_nascita == UA

    print("\u2713 PASS \u2014 inference suggests correctly and stays advisory.")
    print("        known names mapped; unknown + ambiguous refused; present values untouched;")
    print("        list-level defaults proposed only with a hint; apply leaves the original intact.")


if __name__ == "__main__":
    main()
