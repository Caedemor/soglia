"""
Soglia — the stage-1 eval harness (the instrument; PLAN-eval-harness.md).

Measures LIVE stage-1 quality at guest-level outcome, never map-level
similarity (rev5 §7: June's park maps were 0/4 on map-parity and the outcome
was perfect). Two verdict channels per list:

  HARD GATES (any failure -> the list FAILS, and a nonzero exit upstream):
    map_valid          the model's text compiles through parse_map_json
    recall             100% of expected persons found (token-multiset match)
    held_arithmetic    sum of held-stay pax == expected held total
    required_fields    per-list dial (expectations key; DEFAULT EMPTY)
    engine_path        the FULL product runs green on the live output:
                       persist -> version_completeness -> PMS artifact ->
                       export -> confirm -> coverage 'full', delta empty
  SOFT METRICS (reported, never failing — the battery's benign-variance
  lesson, rev5 §8): junk disposition, default_role choice, field-coverage
  deltas, extras (junk-as-guest is emit-and-flag working), completeness
  status, K-run stability.

Ground truth is a small human-authored EXPECTATIONS file per list
(eval/expectations/<list>.json) — persons by name, held pax total, junk
count, field coverage — measuring the model against the DOCUMENT, not our
mapping opinions. The dev four are bootstrapped from the pinned hand parses
and frozen as static files (plan §7).

Callers are injected (the llm_parser seam): live runs belong to the machine
with the key; this module is fully exercisable hermetically — including its
failure modes — which is what suite 15 does. The §3 self-check enters at
evaluate_transcribed: hand maps carry python callables the json contract
cannot express, so the self-check scores the hand PARSE, not a serialized
hand map.
"""
import collections
import datetime
import json
import os

from export import build_pms_csv
from llm_parser import build_prompt, parse_map_json
from parser import transcribe_with_stays
from storage import (connect, init_db, save_list, load_guests_with_ids,
                     record_pms_export, confirm_export, pms_delta,
                     export_coverage, version_completeness)

EXPECTATIONS_DIR = os.path.join(os.path.dirname(__file__), "eval", "expectations")
SCORECARDS_DIR = os.path.join(os.path.dirname(__file__), "eval", "scorecards")


# --- person matching: casefolded token multisets (plan call 3) ------------------

def _person_key(name):
    """Order-insensitive, casefolded token multiset — robust to slot-order
    flips ('KOWALCZYK ANNA' == 'ANNA KOWALCZYK'); duplicates are handled by
    counting keys, not by set collapse."""
    return tuple(sorted(t for t in name.casefold().split() if t))


def match_persons(expected_names, guests):
    """-> (missing_names, extras_count, matched_count). A guest matches an
    expected person iff their token multisets are equal."""
    have = collections.Counter(
        _person_key(f"{g.cognome} {g.nome}") for g in guests)
    missing = []
    for name in expected_names:
        k = _person_key(name)
        if have[k] > 0:
            have[k] -= 1
        else:
            missing.append(name)
    extras = sum(have.values())
    return missing, extras, len(expected_names) - len(missing)


# --- the gate/metric core over an already-transcribed result --------------------

def _field_coverage(guests, expected_names):
    """Non-empty counts per canonical field, over guests matched to real
    persons only (junk-as-guest must not inflate coverage)."""
    keys = {_person_key(n) for n in expected_names}
    real = [g for g in guests
            if _person_key(f"{g.cognome} {g.nome}") in keys]
    fields = ["sesso", "data_nascita", "cittadinanza",
              "tipo_documento", "numero_documento"]
    return {f: sum(1 for g in real if getattr(g, f)) for f in fields}


def evaluate_transcribed(res, expectations):
    """Gates + soft metrics for one transcription. Also the §3 SELF-CHECK's
    entry point: each dev list's HAND parse must ace its own expectations
    file, or the expectations are wrong."""
    out = {"gates": {}, "soft": {}}
    missing, extras, matched = match_persons(expectations["persons"],
                                             res.guests)
    out["gates"]["recall"] = not missing
    if missing:
        out["gates"]["missing_persons"] = missing
    held = sum(s.pax_expected for s in res.stays
               if s.status == "names_pending")
    out["gates"]["held_arithmetic"] = held == expectations["held_pax_total"]
    out["soft"].update({
        "guests": len(res.guests), "matched": matched, "extras": extras,
        "held_pax": held,
        "unrecognized": sum(1 for s in res.stays
                            if s.status == "unrecognized"),
        "flagged": sum(1 for g in res.guests if g.skip_flag),
        "field_coverage": _field_coverage(res.guests,
                                          expectations["persons"]),
    })

    req = expectations.get("required_fields", [])
    if req:
        cov = out["soft"]["field_coverage"]
        n = len(expectations["persons"])
        short = {f: cov.get(f, 0) for f in req if cov.get(f, 0) < n}
        out["gates"]["required_fields"] = not short
        if short:
            out["gates"]["required_fields_short"] = short

    # the engine gate: the product is the pipeline, not the map (plan §7)
    db = f"/tmp/soglia_eval_{os.getpid()}.db"
    if os.path.exists(db):
        os.remove(db)
    try:
        c = connect(db)
        init_db(c)
        vid = save_list(c, res.guests, hotel="eval", source_filename="eval",
                        stays=res.stays)
        vc = version_completeness(c, vid)
        out["soft"]["completeness"] = vc["status"]
        ids = [gid for gid, _ in load_guests_with_ids(c, vid)]
        sid = record_pms_export(c, vid, ids,
                                build_pms_csv(res.guests, res.stays))
        confirm_export(c, sid, actor="eval-harness")
        ok = export_coverage(c, vid) == "full" and pms_delta(c, vid) == []
        c.close()
        out["gates"]["engine_path"] = ok
    except Exception as e:
        out["gates"]["engine_path"] = False
        out["gates"]["engine_error"] = f"{type(e).__name__}: {e}"
    finally:
        if os.path.exists(db):
            os.remove(db)
    return out


def evaluate_run(rows, expectations, map_text):
    """One list, one model answer. Never raises for a bad map: map_invalid
    is a VERDICT, not a crash."""
    out = {"gates": {}, "soft": {}}
    try:
        cmap, review_notes = parse_map_json(map_text)
    except Exception as e:
        out["gates"]["map_valid"] = False
        out["gates"]["map_error"] = f"{type(e).__name__}: {e}"
        return out
    out = evaluate_transcribed(transcribe_with_stays(rows, cmap),
                               expectations)
    out["gates"]["map_valid"] = True
    out["soft"]["review_notes"] = review_notes
    out["soft"]["default_role"] = cmap.default_role
    return out


def evaluate_list(rows, expectations, map_texts, handmap_names=None):
    """One list, K model answers -> the per-list verdict: gates pass iff
    they pass in EVERY run; stability and hand-map outcome parity (dev
    lists' bonus, plan call 1) are soft."""
    runs = [evaluate_run(rows, expectations, t) for t in map_texts]
    gates = {}
    for name in ("map_valid", "recall", "held_arithmetic",
                 "required_fields", "engine_path"):
        vals = [r["gates"][name] for r in runs if name in r["gates"]]
        if vals:
            gates[name] = all(vals)
    fail_detail = [r["gates"] for r in runs
                   if not all(v for v in r["gates"].values()
                              if isinstance(v, bool))]
    stable = len({json.dumps(r["soft"], sort_keys=True, default=str)
                  for r in runs}) == 1
    out = {
        "passed": bool(gates) and all(gates.values()),
        "gates": gates,
        "fail_detail": fail_detail,
        "runs": runs,
        "stability": {"runs": len(runs), "identical_outcomes": stable},
    }
    if handmap_names is not None:
        hand = collections.Counter(_person_key(n) for n in handmap_names)
        out["handmap_parity"] = [
            collections.Counter(
                _person_key(f"{g.cognome} {g.nome}")
                for g in transcribe_with_stays(
                    rows, parse_map_json(t)[0]).guests) == hand
            if r["gates"].get("map_valid") else False
            for t, r in zip(map_texts, runs)]
    return out


# --- corpus + scorecard ----------------------------------------------------------

def load_expectations(list_name):
    with open(os.path.join(EXPECTATIONS_DIR, f"{list_name}.json")) as f:
        return json.load(f)


def guard_path(path):
    """The holdout is never eval data: eval lists become tuning data through
    use; real-data/ stays the untouched final exam."""
    if "real-data" in os.path.abspath(path).split(os.sep):
        raise ValueError(f"refusing a list under real-data/ — the holdout "
                         f"is sealed: {path}")


def run_corpus(corpus, caller_factory, runs=2, label="eval", live=False,
               capture_dir=None):
    """corpus: [(name, rows, expectations)] or with a 4th element
    handmap_names. caller_factory: list_name -> (prompt_text -> map_text) —
    a factory because replay needs a per-list fixture while live ignores
    the name. Orchestrates and records; commits nothing."""
    card = {"meta": {"date": datetime.date.today().isoformat(),
                     "label": label, "runs_per_list": runs, "live": live},
            "lists": {}, "summary": {}}
    for entry in corpus:
        name, rows, exp = entry[0], entry[1], entry[2]
        hand = entry[3] if len(entry) > 3 else None
        caller = caller_factory(name)
        prompt = build_prompt(rows)
        texts = []
        for i in range(runs):
            t = caller(prompt)
            texts.append(t)
            if capture_dir:
                p = os.path.join(
                    capture_dir,
                    f"{name}.{card['meta']['date']}.run{i + 1}.live.json")
                with open(p, "w") as f:
                    json.dump({"list": name, "run": i + 1,
                               "raw_model_output": t}, f, indent=1)
        card["lists"][name] = evaluate_list(rows, exp, texts,
                                            handmap_names=hand)
    passed = [n for n, r in card["lists"].items() if r["passed"]]
    failed = [n for n, r in card["lists"].items() if not r["passed"]]
    card["summary"] = {"passed": passed, "failed": failed,
                       "verdict": "PASS" if not failed else "FAIL"}
    return card


def render_md(card):
    """The human half of the record."""
    m = card["meta"]
    L = [f"# Stage-1 eval scorecard — {m['date']} ({m['label']})",
         f"{'LIVE' if m['live'] else 'offline'}, {m['runs_per_list']} run(s) "
         f"per list — verdict: **{card['summary']['verdict']}**", ""]
    for name, r in card["lists"].items():
        L.append(f"## {name}: {'PASS' if r['passed'] else '**FAIL**'}")
        L.append("gates: " + ", ".join(
            f"{k}={'ok' if v else 'FAIL'}" for k, v in r["gates"].items()))
        soft = next((x["soft"] for x in r["runs"] if x.get("soft")), {})
        if "guests" in soft:
            L.append(f"guests {soft['guests']} (matched {soft['matched']}, "
                     f"extras {soft['extras']}); held {soft['held_pax']}; "
                     f"flagged {soft['flagged']}, unrecognized "
                     f"{soft['unrecognized']}; role "
                     f"{soft.get('default_role', '-')}; completeness "
                     f"{soft.get('completeness', '-')}")
            L.append(f"coverage: {soft['field_coverage']}")
        for fd in r["fail_detail"]:
            L.append(f"  - fail detail: {fd}")
        if "handmap_parity" in r:
            L.append(f"hand-map outcome parity: {r['handmap_parity']}")
        L.append(f"stability: {r['stability']}")
        L.append("")
    return "\n".join(L) + "\n"


def write_scorecard(card, out_dir=SCORECARDS_DIR):
    os.makedirs(out_dir, exist_ok=True)
    base = f"{card['meta']['date']}-{card['meta']['label']}"
    jp = os.path.join(out_dir, base + ".json")
    with open(jp, "w") as f:
        json.dump(card, f, indent=1, sort_keys=True)
    with open(os.path.join(out_dir, base + ".md"), "w") as f:
        f.write(render_md(card))
    return jp
