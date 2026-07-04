"""
Tests for the two audited human assertions (commit 4 of addendum §8.5.8 —
the FINALE). No pytest:
    python3 test_audit.py

What must hold, per PLAN-audit-override.md:
  - mark-complete-despite-pending records {actor, ts, pending_at_override,
    unrecognized_at_override, reason} on the VERSION and is refused when
    there is nothing to vouch for or when already vouched;
  - the override is PER-VERSION: a supplement creates a new version that
    honestly reads awaiting again — new facts, new responsibility;
  - computed truth beats the label: a genuinely complete reconciliation
    reports `complete` even with override=True;
  - confirm-export records {actor, ts, guest_count} — whose belief, when;
    `actor` is REQUIRED (an unattributed audit is hollow);
  - the regeneration corner (commit-2 review finding) is fixed: identical
    bytes after an intervening export mint a FRESH submission under a
    suffixed key; true double-clicks still dedupe;
  - a commit-3-era database migrates in place.

Dev lists only; holdout sealed.
"""
import json
import os
import sqlite3

from export import build_pms_csv
from maps import parse_park_stays, read_docx_rows, MIX18_DOCX, MIX18_MAP
from parser import transcribe_with_stays, ColumnMap, NameSlot
from stay import completeness_status
from storage import (connect, init_db, save_list, load_guests_with_ids,
                     record_pms_export, confirm_export, load_submissions,
                     load_results, export_coverage, apply_supplement,
                     mark_complete_override, version_completeness)

DB = "/tmp/soglia_test_audit.db"
_SUPP_MAP = ColumnMap(header_rows=0, default_role="20",
                      name_slots=[NameSlot(surname_column=1, firstname_column=2)])


def _fresh(guests, stays=None):
    if os.path.exists(DB):
        os.remove(DB)
    c = connect(DB)
    init_db(c)
    vid = save_list(c, guests, hotel="Hotel Continentale",
                    source_filename="x", stays=stays)
    return c, vid


# --- mark-complete: the record, the refusals, the per-version rule --------------
def test_mark_complete_assertion():
    res = parse_park_stays()                 # awaiting: 18 pending
    c, vid = _fresh(res.guests, res.stays)

    rec = mark_complete_override(c, vid, actor="wardo",
                                 reason="last 18 entered in the PMS by hand")
    assert rec["actor"] == "wardo" and "T" in rec["ts"]
    assert (rec["pending_at_override"], rec["unrecognized_at_override"]) == (18, 0)
    assert rec["reason"].startswith("last 18")
    # the stored json parses back to exactly the returned record
    stored = c.execute("SELECT completeness_override FROM list_version "
                       "WHERE id = ?", (vid,)).fetchone()[0]
    assert json.loads(stored) == rec, "the record IS the artifact"

    vc = version_completeness(c, vid)
    assert vc["status"] == "complete_by_override"
    assert (vc["expected"], vc["named"], vc["pending"]) == (41, 23, 18), \
        "the arithmetic stays honest underneath the vouch"

    # refusals: double-override; genuinely-complete
    try:
        mark_complete_override(c, vid, actor="wardo", reason="again")
        assert False, "double-override must be refused — the first record stands"
    except ValueError:
        pass
    c.close()

    m = transcribe_with_stays(read_docx_rows(MIX18_DOCX), MIX18_MAP)
    c2, vid2 = _fresh(m.guests, m.stays)     # genuinely complete (39/39)
    assert version_completeness(c2, vid2)["status"] == "complete"
    try:
        mark_complete_override(c2, vid2, actor="wardo", reason="pointless")
        assert False, "overriding a complete version must be refused"
    except ValueError:
        pass
    c2.close()
    print("PASS mark-complete: record faithful (18 pending vouched), "
          "double-override + nothing-to-vouch refused")


# --- vouching past the floor: unrecognized-only override ------------------------
def test_unrecognized_only_vouch():
    res = transcribe_with_stays(
        [["", "ROSSI", "Mario"], ["Totale: 9", "", ""]], _SUPP_MAP)
    c, vid = _fresh(res.guests, res.stays)
    vc = version_completeness(c, vid)
    assert (vc["pending"], vc["unrecognized"], vc["status"]) == \
        (0, 1, "awaiting_completion"), "the floor blocks on its own"

    rec = mark_complete_override(c, vid, actor="wardo",
                                 reason="checked row 1: a totals line, not a person")
    assert (rec["pending_at_override"], rec["unrecognized_at_override"]) == (0, 1), \
        "vouching past an unrecognized row must SAY so (plan call 3)"
    assert version_completeness(c, vid)["status"] == "complete_by_override"
    c.close()
    print("PASS unrecognized-only vouch: the extension key records what "
          "the human actually looked past")


# --- per-version semantics + computed truth beats the label ----------------------
def test_supplement_resets_assertion():
    res = parse_park_stays()
    c, v1 = _fresh(res.guests, res.stays)
    mark_complete_override(c, v1, actor="wardo", reason="hand-entered")
    assert version_completeness(c, v1)["status"] == "complete_by_override"

    supp = transcribe_with_stays([["", f"S{i}", "X"] for i in range(5)], _SUPP_MAP)
    v2 = apply_supplement(c, v1, supp, source_filename="supp.txt")
    vc2 = version_completeness(c, v2)
    assert vc2["status"] == "awaiting_completion" and vc2["pending"] == 13, \
        "new facts, new responsibility: the assertion does NOT carry forward"
    assert version_completeness(c, v1)["status"] == "complete_by_override", \
        "…while the old version keeps its record (versions are the history)"
    c.close()

    # computed truth beats the label (pure-function pin — within one version
    # the API refuses this state, so it is pinned at the function level):
    complete = {"expected": 5, "named": 5, "pending": 0, "overage": 0,
                "unrecognized": 0}
    assert completeness_status(complete, override=True) == "complete"
    assert completeness_status({**complete, "pending": 2},
                               override=True) == "complete_by_override"
    print("PASS per-version: supplement resets to awaiting; old record stands; "
          "genuine completeness outranks the label")


# --- confirm-export: the belief, logged ------------------------------------------
def test_export_confirm_record():
    res = parse_park_stays()
    c, vid = _fresh(res.guests, res.stays)
    ids = [gid for gid, _ in load_guests_with_ids(c, vid)]
    sid = record_pms_export(c, vid, ids, build_pms_csv(res.guests, res.stays))
    confirm_export(c, sid, actor="wardo")

    sub = load_submissions(c, vid)[0]
    record = json.loads(sub.export_confirm)
    assert record["actor"] == "wardo" and record["guest_count"] == 23 \
        and "T" in record["ts"], "whose belief, and when"

    # a generated-then-superseded submission never gains a record
    s2 = record_pms_export(c, vid, ids[:3], "A")
    s3 = record_pms_export(c, vid, ids[:4], "B")
    subs = {s.id: s for s in load_submissions(c, vid)}
    assert subs[s2].export_confirm == "" and subs[s3].export_confirm == ""

    # actor is REQUIRED — an unattributed audit record is hollow
    try:
        confirm_export(c, s3)
        assert False, "confirm without actor must be a TypeError"
    except TypeError:
        pass
    c.close()
    print("PASS confirm-export: {actor, ts, guest_count} recorded at confirm "
          "only; actor required by signature")


# --- the regeneration corner, fixed ----------------------------------------------
def test_regeneration_corner():
    res = parse_park_stays()
    c, vid = _fresh(res.guests, res.stays)
    ids = [gid for gid, _ in load_guests_with_ids(c, vid)]
    text = build_pms_csv(res.guests, res.stays)

    a = record_pms_export(c, vid, ids, text)
    b = record_pms_export(c, vid, ids[:5], "other")        # supersedes a
    regen = record_pms_export(c, vid, ids, text)           # identical bytes
    assert regen not in (a, b), "regeneration after an intervening export " \
        "mints a FRESH submission (the commit-2 review corner, fixed)"
    subs = {s.id: s for s in load_submissions(c, vid)}
    assert subs[regen].idempotency_key.endswith("|r2"), \
        "the regeneration lineage is auditable in the key itself"
    assert subs[regen].status == "generated" and subs[a].status == "superseded"
    assert load_results(c, regen) and \
        [r.guest_id for r in load_results(c, regen)] == sorted(ids)

    # a true double-click on the regenerated one still dedupes
    assert record_pms_export(c, vid, ids, text) == regen
    # …and it confirms — the old refusal now only guards genuinely stale ids
    confirm_export(c, regen, actor="wardo")
    assert export_coverage(c, vid) == "full"
    try:
        confirm_export(c, a, actor="wardo")
        assert False, "the stale-bytes refusal stays as defense-in-depth"
    except ValueError:
        pass
    # a third generation round suffixes deeper
    record_pms_export(c, vid, ids[:5], "other2")           # supersedes regen
    r3 = record_pms_export(c, vid, ids, text)
    assert {s.id: s for s in load_submissions(c, vid)}[r3] \
        .idempotency_key.endswith("|r3")
    c.close()
    print("PASS regeneration corner: fresh mint (|r2, |r3), double-click still "
          "dedupes, stale-confirm refusal retained")


# --- a commit-3-era database migrates in place ------------------------------------
def test_migration_commit3_era():
    if os.path.exists(DB):
        os.remove(DB)
    legacy = sqlite3.connect(DB)   # commit-3 schema: NO completeness_override
    legacy.executescript("""
        CREATE TABLE guest_list (id INTEGER PRIMARY KEY AUTOINCREMENT,
                                 hotel TEXT, created_at TEXT);
        CREATE TABLE list_version (id INTEGER PRIMARY KEY AUTOINCREMENT,
                                   guest_list_id INTEGER, source_filename TEXT,
                                   created_at TEXT,
                                   relation_to_prior TEXT DEFAULT '');
        CREATE TABLE guest (id INTEGER PRIMARY KEY AUTOINCREMENT,
            list_version_id INTEGER, idx INTEGER, tipo_alloggiato TEXT,
            cognome TEXT, nome TEXT, sesso TEXT, data_nascita TEXT,
            born_in_italy INTEGER, comune_nascita TEXT, provincia_nascita TEXT,
            stato_nascita TEXT, cittadinanza TEXT, tipo_documento TEXT,
            numero_documento TEXT, luogo_rilascio TEXT,
            skip_flag TEXT DEFAULT '', stay_id INTEGER);
        CREATE TABLE guest_lineage (guest_id INTEGER PRIMARY KEY,
                                    prior_guest_id INTEGER);
        CREATE TABLE stay (id INTEGER PRIMARY KEY AUTOINCREMENT,
            list_version_id INTEGER, stay_id INTEGER, pax_expected INTEGER,
            status TEXT, verbatim TEXT, source_row INTEGER);
        CREATE TABLE submission (id INTEGER PRIMARY KEY AUTOINCREMENT,
            list_version_id INTEGER, target TEXT, idempotency_key TEXT UNIQUE,
            status TEXT, submitted_arrival_date TEXT, artifact_hash TEXT,
            submitted_at TEXT, export_confirm TEXT DEFAULT '');
        CREATE TABLE submission_result (id INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_id INTEGER, guest_id INTEGER, outcome TEXT,
            portal_line_no INTEGER, portal_reason TEXT DEFAULT '');
    """)
    legacy.close()
    c = connect(DB)
    init_db(c)                     # ALTER adds completeness_override
    res = parse_park_stays()
    vid = save_list(c, res.guests, hotel="x", source_filename="x",
                    stays=res.stays)
    mark_complete_override(c, vid, actor="wardo", reason="migration check")
    assert version_completeness(c, vid)["status"] == "complete_by_override"
    c.close()
    os.remove(DB)
    print("PASS commit-3-era DB migrated in place; the assertion works on it")


if __name__ == "__main__":
    test_mark_complete_assertion()
    test_unrecognized_only_vouch()
    test_supplement_resets_assertion()
    test_export_confirm_record()
    test_regeneration_corner()
    test_migration_commit3_era()
    print("ALL GREEN")
