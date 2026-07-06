"""
Tests for the stage-1 eval harness (PLAN-eval-harness.md). No pytest:
    python3 test_eval_harness.py

What must hold:
  - the §3 SELF-CHECK: every dev list's HAND parse aces its own
    expectations file — if our best-understood parse can't pass, the
    expectations are wrong, and this suite says so before any live run
    consumes them;
  - the gate taxonomy: missing person / invalid map / held arithmetic /
    required-fields dial / engine path fail HARD, with the failure named;
    junk disposition, role, coverage deltas, extras, stability stay SOFT;
  - person matching is order-insensitive and duplicate-correct;
  - a bad model answer is a VERDICT (map_invalid), never a crash;
  - the replay corpus (tracked fixtures) passes end-to-end and its known
    benign divergences land exactly where the battery measured them;
  - real-data/ is refused (the holdout stays sealed);
  - scorecards are deterministic and render.

Dev lists only; live runs belong to the machine with the key.
"""
import json
import os

from eval_harness import (_person_key, match_persons, evaluate_transcribed,
                          evaluate_run, evaluate_list, load_expectations,
                          guard_path, run_corpus, render_md, write_scorecard)
from llm_parser import replay_caller
from maps import (parse_mix18, parse_polish, parse_park_stays,
                  read_docx_rows, read_xlsx_rows, read_text_rows,
                  MIX18_DOCX, POLISH_XLSX, PARK_XLSX, TEXTMAIL_TXT,
                  TEXTMAIL_MAP)
from parser import transcribe_with_stays
from tracciato import Guest


def _g(cognome, nome):
    return Guest(tipo_alloggiato="20", cognome=cognome, nome=nome,
                 sesso="", data_nascita="", stato_nascita="", cittadinanza="")


# --- person matching: the correctness core ---------------------------------------
def test_matcher():
    assert _person_key("KOWALCZYK Anna") == _person_key("anna kowalczyk"), \
        "order-insensitive, casefolded"
    guests = [_g("ROSSI", "Mario"), _g("ROSSI", "Mario"), _g("VERDI", "Anna")]
    missing, extras, matched = match_persons(
        ["ROSSI Mario", "ROSSI Mario", "VERDI Anna"], guests)
    assert (missing, extras, matched) == ([], 0, 3), \
        "duplicate full names are counted, not set-collapsed"
    missing, extras, matched = match_persons(
        ["ROSSI Mario", "ROSSI Mario"], guests[:1] + guests[2:])
    assert missing == ["ROSSI Mario"] and extras == 1, \
        "the second Mario is missing BY NAME; Anna counts as an extra"
    print("PASS matcher: order flips, duplicates, misses named, extras counted")


# --- the §3 self-check: hand parses ace their own expectations --------------------
def test_self_check_dev_corpus():
    class R:
        def __init__(self, guests, stays=None):
            self.guests, self.stays = guests, stays or []

    cases = {
        "mix18": R(parse_mix18()),
        "polish": R(parse_polish()),
        "park": parse_park_stays(),
        "textmail": transcribe_with_stays(read_text_rows(TEXTMAIL_TXT),
                                          TEXTMAIL_MAP),
    }
    for name, res in cases.items():
        exp = load_expectations(name)
        out = evaluate_transcribed(res, exp)
        gates = {k: v for k, v in out["gates"].items()
                 if isinstance(v, bool)}
        assert gates and all(gates.values()), f"{name}: {out['gates']}"
        assert out["soft"]["completeness"] == exp["completeness"]
    # polish's 7 junk-guests are EXTRAS (soft), never a gate failure
    polish = evaluate_transcribed(cases["polish"], load_expectations("polish"))
    assert polish["soft"]["extras"] == 7 and polish["soft"]["flagged"] == 7
    print("PASS self-check: all four hand parses ace their expectations; "
          "polish junk lands soft")


# --- gate taxonomy on a surgical synthetic list -----------------------------------
_ROWS = [["", "ROSSI Mario", ""], ["", "VERDI Anna", ""],
         ["+ 3 pax", "", ""]]
_EXP = {"list": "synthetic", "persons": ["ROSSI Mario", "VERDI Anna"],
        "held_pax_total": 3, "junk_rows": 0, "field_coverage": {},
        "required_fields": [], "completeness": "awaiting_completion"}
_GOOD_MAP = json.dumps({
    "header_rows": 0, "default_role": "20",
    "name_slots": [{"surname_column": 1, "combined": True,
                    "name_order": "surname_first"}],
    "fields": {}, "review_notes": []})


def test_gates_and_failure_modes():
    ok = evaluate_run(_ROWS, _EXP, _GOOD_MAP)
    assert all(v for v in ok["gates"].values() if isinstance(v, bool)), ok
    assert ok["soft"]["held_pax"] == 3 and ok["soft"]["matched"] == 2

    # a bad model answer is a verdict, not a crash
    bad = evaluate_run(_ROWS, _EXP, "{not json at all")
    assert bad["gates"]["map_valid"] is False and "map_error" in bad["gates"]

    # header bump swallows the first person -> recall FAILS, named
    bump = json.loads(_GOOD_MAP); bump["header_rows"] = 1
    r = evaluate_run(_ROWS, _EXP, json.dumps(bump))
    assert r["gates"]["recall"] is False
    assert r["gates"]["missing_persons"] == ["ROSSI Mario"]

    # a map that pulls the trailer INTO the slots breaks held arithmetic
    slot0 = json.loads(_GOOD_MAP)
    slot0["name_slots"] = [{"surname_column": 0, "combined": True,
                            "name_order": "surname_first"}]
    r = evaluate_run(_ROWS, _EXP, json.dumps(slot0))
    assert r["gates"]["held_arithmetic"] is False, \
        "a phantom-guest trailer must fail the arithmetic gate"

    # per-list verdict: gates must hold in EVERY run
    lst = evaluate_list(_ROWS, _EXP, [_GOOD_MAP, json.dumps(bump)])
    assert lst["passed"] is False and lst["gates"]["recall"] is False
    assert lst["stability"]["identical_outcomes"] is False
    lst = evaluate_list(_ROWS, _EXP, [_GOOD_MAP, _GOOD_MAP])
    assert lst["passed"] is True and lst["stability"]["identical_outcomes"]
    print("PASS gates: invalid map / missing person (named) / broken held "
          "arithmetic fail hard; every-run rule; stability surfaces")


# --- the required_fields dial (default empty; user's per-list promotion) ----------
def test_required_fields_dial():
    rows = [["", "ROSSI Mario", "01.01.1990"]]
    exp = {"list": "s", "persons": ["ROSSI Mario"], "held_pax_total": 0,
           "junk_rows": 0, "field_coverage": {},
           "required_fields": ["data_nascita"], "completeness": "complete"}
    with_dob = json.dumps({
        "header_rows": 0, "default_role": "20",
        "name_slots": [{"surname_column": 1, "combined": True,
                        "name_order": "surname_first"}],
        "fields": {"data_nascita": {"column": 2,
                                    "normalizer": "dotted_date"}},
        "review_notes": []})
    r = evaluate_run(rows, exp, with_dob)
    assert r["gates"]["required_fields"] is True
    r = evaluate_run(rows, exp, _GOOD_MAP)     # dob not mapped
    assert r["gates"]["required_fields"] is False
    assert r["gates"]["required_fields_short"] == {"data_nascita": 0}
    print("PASS required_fields dial: promoted field gates; default stays off")


# --- the replay corpus: fixtures through the whole instrument ---------------------
def test_replay_corpus_pin():
    corpus = []
    for name, reader, path, hand in [
            ("mix18", read_docx_rows, MIX18_DOCX, parse_mix18()),
            ("polish", read_xlsx_rows, POLISH_XLSX, parse_polish()),
            ("park", read_xlsx_rows, PARK_XLSX, parse_park_stays().guests)]:
        corpus.append((name, reader(path), load_expectations(name),
                       [f"{g.cognome} {g.nome}".strip() for g in hand]))
    factory = lambda name: replay_caller(f"llm_maps/{name}.json")
    card = run_corpus(corpus, factory, runs=1, label="test-replay")
    assert card["summary"]["verdict"] == "PASS", card["summary"]
    park = card["lists"]["park"]["runs"][0]["soft"]
    assert (park["guests"], park["held_pax"]) == (23, 18)
    polish = card["lists"]["polish"]["runs"][0]["soft"]
    assert polish["matched"] == 48, \
        "every real person, whatever the junk disposition (rev5 §7)"
    assert card["lists"]["mix18"]["handmap_parity"] == [True]
    assert card["lists"]["park"]["handmap_parity"] == [True]
    print(f"PASS replay corpus: verdict PASS; park 23+18; polish 48/48 real "
          f"(disposition: {polish['flagged']} flagged, "
          f"{polish['extras']} extras); parity bonus works")


# --- rails + record ---------------------------------------------------------------
def test_guard_and_record():
    try:
        guard_path("real-data/holdout.xlsx")
        assert False, "the holdout must be refused"
    except ValueError as e:
        assert "sealed" in str(e)
    guard_path("data/anything.xlsx")     # fine

    card_a = run_corpus([("s", _ROWS, _EXP)],
                        lambda n: (lambda p: _GOOD_MAP), runs=2, label="d")
    card_b = run_corpus([("s", _ROWS, _EXP)],
                        lambda n: (lambda p: _GOOD_MAP), runs=2, label="d")
    assert json.dumps(card_a, sort_keys=True) == \
        json.dumps(card_b, sort_keys=True), "scorecards are deterministic"
    md = render_md(card_a)
    assert "PASS" in md and "held 3" in md
    path = write_scorecard(card_a, out_dir="/tmp/soglia_eval_cards")
    assert os.path.exists(path) and os.path.exists(
        path.replace(".json", ".md"))
    print("PASS rails: real-data refused; deterministic scorecard; "
          "json+md written")


if __name__ == "__main__":
    test_matcher()
    test_self_check_dev_corpus()
    test_gates_and_failure_modes()
    test_required_fields_dial()
    test_replay_corpus_pin()
    test_guard_and_record()
    print("ALL GREEN")
