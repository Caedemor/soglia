"""
Tests for export-state tracking + delta export (commit 2 of addendum §8.5.8).
No pytest:
    python3 test_export.py

What must hold, per PLAN-export-state.md:
  - generation appends a SUBMISSION(pms, generated) + a manifest for exactly
    the guest set the artifact was built from; the artifact is deterministic;
    a double-click records nothing twice (§13.9);
  - only CONFIRMED exports flip guests to exported; coverage and the delta
    are pure set membership over confirmed results;
  - re-export appends and supersedes, never deletes; a confirmed-then-
    superseded export's guests STAY covered (superseded != invalidated);
  - confirming a superseded submission is refused (stale bytes);
  - the two §8.5.1 axes are orthogonal: textmail reaches coverage=full while
    completeness stays awaiting_completion (2 held pax) — the flagship;
  - the delta includes red/flagged guests on purpose (loud, never silent);
  - alloggiati hand-offs are recorded minimally with §13.2's arrival stamp.

Dev lists only; holdout sealed.
"""
import os
import sqlite3

from export import build_pms_csv, PMS_CSV_COLUMNS
from maps import (parse_park_stays, parse_polish, read_text_rows,
                  TEXTMAIL_TXT, TEXTMAIL_MAP)
from parser import transcribe_with_stays
from stay import Stay, reconcile, completeness_status
from storage import (connect, init_db, save_list, load_guests_with_ids,
                     record_pms_export, confirm_export,
                     record_alloggiati_submission, pms_delta, export_coverage,
                     load_submissions, load_results)
from validate import is_submittable

DB = "/tmp/soglia_test_export.db"


def _fresh(guests, stays=None):
    if os.path.exists(DB):
        os.remove(DB)
    c = connect(DB)
    init_db(c)
    vid = save_list(c, guests, hotel="Hotel Continentale",
                    source_filename="x", stays=stays)
    return c, vid


# --- the artifact: deterministic, lens-correct, loud ---------------------------
def test_artifact():
    res = parse_park_stays()
    text = build_pms_csv(res.guests, res.stays)
    lines = text.split("\n")
    assert lines[0] == ",".join(PMS_CSV_COLUMNS)
    assert len([l for l in lines if l.startswith("guest,")]) == 23
    held_lines = [l for l in lines if l.startswith("held_names_pending,")]
    assert len(held_lines) == 9 and all("Al.Mat" in l for l in held_lines), \
        "held stays are bookings and ride into the artifact (§8.5.7)"
    assert build_pms_csv(res.guests, res.stays) == text, "artifact must be deterministic"

    # unrecognized stays are attention items, NOT hand-off content
    with_unrec = res.stays + [Stay(stay_id=99, pax_expected=0,
                                   status="unrecognized", verbatim="Totale: 47")]
    assert "unrecognized" not in build_pms_csv(res.guests, with_unrec)
    assert "Totale: 47" not in build_pms_csv(res.guests, with_unrec)

    # red guests are still bookings: polish's guard-red drivers appear
    polish_csv = build_pms_csv(parse_polish(), [])
    assert any(l.startswith("guest,") and "Driver" in l
               for l in polish_csv.split("\n")), \
        "a named-but-red guest is still a real booking on the logistics lens"
    print("PASS artifact: header + 23 guests + 9 held (park), deterministic; "
          "unrecognized excluded; red guests included")


# --- generation: manifest, idempotency, supersede-on-append --------------------
def test_generation_and_idempotency():
    res = parse_park_stays()
    c, vid = _fresh(res.guests, res.stays)
    pairs = load_guests_with_ids(c, vid)
    assert [g for _, g in pairs] == res.guests, "ids loader must preserve order+content"
    ids = [gid for gid, _ in pairs]
    text = build_pms_csv(res.guests, res.stays)

    sid = record_pms_export(c, vid, ids, text)
    subs = load_submissions(c, vid)
    assert len(subs) == 1 and subs[0].status == "generated"
    assert subs[0].target == "pms" and len(subs[0].artifact_hash) == 64
    manifest = load_results(c, sid)
    assert len(manifest) == 23 and all(r.outcome == "" for r in manifest), \
        "generation writes the MANIFEST; outcomes arrive only at confirm"

    # a manifest is not coverage: nothing is exported yet
    assert export_coverage(c, vid) == "none"
    assert len(pms_delta(c, vid)) == 23, "delta unchanged until confirm"

    # double-click: the same hand-off records once (§13.9)
    assert record_pms_export(c, vid, ids, text) == sid
    assert len(load_submissions(c, vid)) == 1

    # a genuinely new export supersedes the prior (doc-literal append rule)
    sid2 = record_pms_export(c, vid, ids[:5], build_pms_csv(res.guests[:5], []))
    statuses = [s.status for s in load_submissions(c, vid)]
    assert statuses == ["superseded", "generated"] and sid2 != sid
    c.close()
    print("PASS generation: manifest written, coverage untouched, double-click "
          "deduped, new export supersedes prior")


# --- confirm: outcomes, coverage, refusal on stale -----------------------------
def test_confirm_and_refusals():
    res = parse_park_stays()
    c, vid = _fresh(res.guests, res.stays)
    ids = [gid for gid, _ in load_guests_with_ids(c, vid)]
    sid = record_pms_export(c, vid, ids, build_pms_csv(res.guests, res.stays))
    confirm_export(c, sid)

    assert all(r.outcome == "exported_unverified" for r in load_results(c, sid))
    assert export_coverage(c, vid) == "full" and pms_delta(c, vid) == []
    assert load_submissions(c, vid)[0].status == "export_confirmed"

    # confirming twice, or confirming a superseded draft, is refused
    for bad in (sid,):
        try:
            confirm_export(c, bad)
            assert False, "re-confirm must be refused"
        except ValueError:
            pass
    sid_a = record_pms_export(c, vid, ids[:3], "A")
    sid_b = record_pms_export(c, vid, ids[:4], "B")     # supersedes sid_a
    try:
        confirm_export(c, sid_a)
        assert False, "confirming a SUPERSEDED submission must be refused"
    except ValueError:
        pass
    confirm_export(c, sid_b)                            # the newest confirms fine
    c.close()
    print("PASS confirm: outcomes written, coverage full, delta empty; "
          "re-confirm and stale-confirm refused")


# --- the stepfather walk + the two-axis flagship --------------------------------
def test_stepfather_and_orthogonality():
    res = transcribe_with_stays(read_text_rows(TEXTMAIL_TXT), TEXTMAIL_MAP)
    c, vid = _fresh(res.guests, res.stays)
    pairs = load_guests_with_ids(c, vid)
    first42 = [gid for gid, _ in pairs[:42]]

    sid = record_pms_export(c, vid, first42,
                            build_pms_csv([g for _, g in pairs[:42]], res.stays))
    confirm_export(c, sid)
    assert export_coverage(c, vid) == "partial"
    delta = pms_delta(c, vid)
    assert [gid for gid, _ in delta] == [gid for gid, _ in pairs[42:]], \
        "the delta is exactly the 5 not yet handed over (the stepfather case)"

    sid2 = record_pms_export(c, vid, [gid for gid, _ in delta],
                             build_pms_csv([g for _, g in delta], res.stays))
    confirm_export(c, sid2)
    # the first export is now superseded — its 42 must STAY covered
    assert load_submissions(c, vid)[0].status == "superseded"
    assert export_coverage(c, vid) == "full", \
        "superseded != invalidated: write-once results keep their force"

    # THE FLAGSHIP (§8.5.1): the two axes are orthogonal. Every named guest
    # is handed to the PMS, yet the list is NOT complete — 2 drivers are
    # still unnamed on the held trailer. One truth per lens.
    rec = reconcile(res.stays, res.guests)
    assert export_coverage(c, vid) == "full" and rec["pending"] == 2
    assert completeness_status(rec) == "awaiting_completion"
    c.close()
    print("PASS stepfather 42+5 walk; FLAGSHIP: coverage=full while "
          "completeness=awaiting_completion — the two axes are orthogonal")


# --- red/flagged guests count, loudly; alloggiati recording --------------------
def test_junk_loud_and_alloggiati():
    polish = parse_polish()
    c, vid = _fresh(polish)
    delta = pms_delta(c, vid)
    assert len(delta) == 55, "ALL persisted guests count (plan §6a)"
    flagged = [g for _, g in delta if g.skip_flag]
    reds = [g for _, g in delta if not is_submittable(g)]
    assert len(flagged) == 7 and reds, \
        "junk fails LOUD in the delta — silent exclusion could drop a real person"

    sid = record_alloggiati_submission(c, vid, "tracciato-bytes", "03/07/2026")
    assert record_alloggiati_submission(c, vid, "tracciato-bytes",
                                        "03/07/2026") == sid
    sub = [s for s in load_submissions(c, vid) if s.target == "alloggiati"][0]
    assert (sub.status, sub.submitted_arrival_date) == ("pending", "03/07/2026"), \
        "§13.2: arrival is stamped at submission time"
    assert load_results(c, sid) == [], "the portal verdict loop is stubbed"
    c.close()
    print("PASS delta includes 7 flagged + red guests (loud); alloggiati "
          "recorded with submit-time arrival, verdict loop stubbed")


# --- legacy migration + round-trip ---------------------------------------------
def test_legacy_migration_and_roundtrip():
    if os.path.exists(DB):
        os.remove(DB)
    legacy = sqlite3.connect(DB)     # a pre-commit-2 database: no submission tables
    legacy.executescript("""
        CREATE TABLE guest_list (id INTEGER PRIMARY KEY AUTOINCREMENT,
                                 hotel TEXT, created_at TEXT);
        CREATE TABLE list_version (id INTEGER PRIMARY KEY AUTOINCREMENT,
                                   guest_list_id INTEGER, source_filename TEXT,
                                   created_at TEXT);
        CREATE TABLE guest (id INTEGER PRIMARY KEY AUTOINCREMENT,
            list_version_id INTEGER, idx INTEGER, tipo_alloggiato TEXT,
            cognome TEXT, nome TEXT, sesso TEXT, data_nascita TEXT,
            born_in_italy INTEGER, comune_nascita TEXT, provincia_nascita TEXT,
            stato_nascita TEXT, cittadinanza TEXT, tipo_documento TEXT,
            numero_documento TEXT, luogo_rilascio TEXT,
            skip_flag TEXT DEFAULT '', stay_id INTEGER);
        CREATE TABLE stay (id INTEGER PRIMARY KEY AUTOINCREMENT,
            list_version_id INTEGER, stay_id INTEGER, pax_expected INTEGER,
            status TEXT, verbatim TEXT, source_row INTEGER);
    """)
    legacy.close()

    c = connect(DB)
    init_db(c)                       # CREATE IF NOT EXISTS adds the two tables
    res = parse_park_stays()
    vid = save_list(c, res.guests, hotel="x", source_filename="x",
                    stays=res.stays)
    ids = [gid for gid, _ in load_guests_with_ids(c, vid)]
    sid = record_pms_export(c, vid, ids, build_pms_csv(res.guests, res.stays))
    confirm_export(c, sid)
    assert export_coverage(c, vid) == "full"
    sub = load_submissions(c, vid)[0]
    assert (sub.id, sub.list_version_id) == (sid, vid), \
        "Submission round-trips with its storage identity"
    c.close()
    os.remove(DB)
    print("PASS legacy DB migrated in place; submission round-trips with id")


if __name__ == "__main__":
    test_artifact()
    test_generation_and_idempotency()
    test_confirm_and_refusals()
    test_stepfather_and_orthogonality()
    test_junk_loud_and_alloggiati()
    test_legacy_migration_and_roundtrip()
    print("ALL GREEN")
