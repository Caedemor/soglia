"""
Tests for NON-DESTRUCTIVE skip handling in stage 2.

Three experiments converged on one failure class: a model-authored skip rule
silently drops rows, which bypasses validate.py because dropped rows are never
transcribed. The fix: a skip rule is a REVIEW HINT, not a delete. A skipped row
that still carries a name is emitted with `skip_flag` set (-> RED -> non-
submittable), so a wrongly-skipped real guest surfaces instead of vanishing.

  (a) a HARMFUL skip (column_empty col5 on mix18) must NOT drop the 3 passport-
      less real guests — they are emitted-and-flagged, and no data changes;
  (b) LEGITIMATE skips of header/legend rows still work and must NOT skip-flag
      any real guest on polish; park's held "Al.Mat" rows are now recognized as
      HELD CAPACITY (stay.py) BEFORE the map's skip rule — they become
      names_pending stays, never guests, and never vanish (§8.5.7);
  (c) deterministic count reconciliation reports the skip AND held deltas.

Dev lists only; holdout sealed.
"""
import dataclasses

from llm_parser import SKIP_RULES
from maps import (read_docx_rows, read_xlsx_rows, MIX18_DOCX, PARK_XLSX,
                  MIX18_MAP, PARK_MAP, parse_mix18, parse_polish, parse_park)
from parser import transcribe, transcribe_report, transcribe_with_stays
from validate import validate_guest, is_submittable


def _name_reds(g):
    return [i for i in validate_guest(g)
            if i.tier == "red" and i.field in ("cognome", "nome")
            and "non sembra un nome" in i.message]

def _data_tuple(g):
    return (g.cognome, g.nome, g.data_nascita, g.numero_documento, g.tipo_alloggiato)


# --- (a) a harmful skip must surface, not delete, the 3 passport-less guests ---
def test_harmful_skip_surfaces_not_drops():
    rows = read_docx_rows(MIX18_DOCX)
    harmful = dataclasses.replace(
        MIX18_MAP,
        skip_row=SKIP_RULES["column_empty"]({"column": 5}),   # the masked-mix18 failure
        skip_desc="column_empty col5")
    live = transcribe(rows, harmful)
    baseline = parse_mix18()                                   # 39, no skip

    # nothing vanished: still 39 emitted, identical DATA (only the flag is added)
    assert len(live) == 39, f"harmful skip dropped rows: got {len(live)}"
    assert {_data_tuple(g) for g in live} == {_data_tuple(g) for g in baseline}

    flagged = [g for g in live if g.skip_flag]
    assert len(flagged) == 3, f"expected 3 passport-less guests flagged, got {len(flagged)}"
    for g in flagged:
        assert not g.numero_documento.strip(), "only the empty-passport rows should match"
        assert not is_submittable(g), "a skip-flagged row must be held back"
        assert "column_empty col5" in g.skip_flag
        # the discriminator: these are REAL names — the name-plausibility guard does
        # NOT flag them; only the skip-flag mechanism surfaces this kind of loss.
        assert not _name_reds(g), f"real name wrongly name-flagged: {g.cognome!r}"
    print("PASS (a) harmful skip surfaces 3 real guests RED, drops nothing, no data change")


# --- (b) legitimate skips still work; held rows outrank them; no real guest hit ---
def test_legitimate_skips_flag_only_nonguests():
    # park: the 9 held "Al.Mat" rows are HELD CAPACITY now — recognized in code
    # before the map's skip rule, so they become names_pending stays, NOT
    # skip-flagged guests. The 23 real crew are guests, none flagged.
    res = transcribe_with_stays(read_xlsx_rows(PARK_XLSX), PARK_MAP)
    assert len(res.guests) == 23, f"park real crew changed: {len(res.guests)}"
    assert all(not g.skip_flag for g in res.guests), "a real crew member was skip-flagged"
    held = [s for s in res.stays if s.status == "names_pending"]
    assert len(held) == 9 and all(s.verbatim.startswith("Al.Mat") for s in held)
    assert sum(s.pax_expected for s in held) == 18, "held pax must match §13.4 (9 twins)"
    held_ids = {s.stay_id for s in held}
    assert all(g.stay_id not in held_ids for g in res.guests), \
        "no guest may sit on a held stay"

    # polish: 7 header/legend rows flagged; the 48 numbered guests untouched
    polish = parse_polish()
    p_flagged = [g for g in polish if g.skip_flag]
    p_real = [g for g in polish if not g.skip_flag]
    assert len(p_real) == 48, f"polish real guests changed: {len(p_real)}"
    assert len(p_flagged) == 7, f"expected 7 header/legend rows flagged, got {len(p_flagged)}"
    # the 2 'Driver N' rows are numbered real-ish rows — caught by the name guard,
    # NOT by the skip rule, so they must carry no skip_flag.
    drivers = [g for g in polish if g.cognome.lower().startswith("driver")]
    assert len(drivers) == 2 and all(not g.skip_flag for g in drivers)
    print("PASS (b) legitimate skips flag only non-guest rows; 0 real guests skip-flagged")


# --- (c) deterministic count reconciliation ----------------------------------
def test_count_reconciliation():
    rows = read_docx_rows(MIX18_DOCX)
    harmful = dataclasses.replace(
        MIX18_MAP, skip_row=SKIP_RULES["column_empty"]({"column": 5}),
        skip_desc="column_empty col5")
    rep = transcribe_report(rows, harmful)
    assert rep.input_rows == len(rows) and rep.guests == 39 and rep.skip_flagged == 3
    assert "column_empty col5" in rep.summary() and "NOT dropped" in rep.summary()

    rep_park = transcribe_report(read_xlsx_rows(PARK_XLSX), PARK_MAP)
    assert rep_park.guests == 23 and rep_park.skip_flagged == 0
    assert rep_park.held_stays == 9 and rep_park.held_pax == 18
    assert "held capacity" in rep_park.summary()
    print("PASS (c) reconciliation reports the skip delta explicitly:")
    print("        " + rep.summary())


if __name__ == "__main__":
    test_harmful_skip_surfaces_not_drops()
    test_legitimate_skips_flag_only_nonguests()
    test_count_reconciliation()
    print("ALL GREEN")
