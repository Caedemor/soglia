"""
Tests for NON-DESTRUCTIVE skip handling in stage 2.

Three experiments converged on one failure class: a model-authored skip rule
silently drops rows, which bypasses validate.py because dropped rows are never
transcribed. The fix: a skip rule is a REVIEW HINT, not a delete. A skipped row
that still carries a name is emitted with `skip_flag` set (-> RED -> non-
submittable), so a wrongly-skipped real guest surfaces instead of vanishing.

  (a) a HARMFUL skip (column_empty col5 on mix18) must NOT drop the 3 passport-
      less real guests — they are emitted-and-flagged, and no data changes;
  (b) LEGITIMATE skips of header/legend/held rows still work and must NOT
      skip-flag any real guest on polish/park;
  (c) deterministic count reconciliation reports the skip delta explicitly.

Dev lists only; holdout sealed.
"""
import dataclasses

from llm_parser import SKIP_RULES
from maps import (read_docx_rows, read_xlsx_rows, MIX18_DOCX, PARK_XLSX,
                  MIX18_MAP, PARK_MAP, parse_mix18, parse_polish, parse_park)
from parser import transcribe, transcribe_report
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


# --- (b) legitimate skips still work; no real guest is skip-flagged ------------
def test_legitimate_skips_flag_only_nonguests():
    # park: 9 held Al.Mat rows flagged; the 23 real crew untouched
    park = parse_park()
    flagged = [g for g in park if g.skip_flag]
    crew = [g for g in park if not g.skip_flag]
    assert len(crew) == 23, f"park real crew changed: {len(crew)}"
    assert len(flagged) == 9 and all(g.cognome.lower().startswith("al.mat") for g in flagged)
    assert all(not g.skip_flag for g in crew), "a real crew member was skip-flagged"

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
    assert rep_park.guests == 32 and rep_park.skip_flagged == 9
    print("PASS (c) reconciliation reports the skip delta explicitly:")
    print("        " + rep.summary())


if __name__ == "__main__":
    test_harmful_skip_surfaces_not_drops()
    test_legitimate_skips_flag_only_nonguests()
    test_count_reconciliation()
    print("ALL GREEN")
