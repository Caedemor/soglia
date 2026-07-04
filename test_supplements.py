"""
Tests for supplement accumulation + mismatch-tolerant reconciliation
(commit 3 of addendum §8.5.8). No pytest:
    python3 test_supplements.py

What must hold, per PLAN-supplements.md:
  - a supplement is a NEW version (relation_to_prior='supplement'); the prior
    version is never touched;
  - carried guests keep their export facts through guest_lineage (a receipt
    of our own copy — NOT the stubbed person_key): the stepfather's 25 stay
    exported, the delta offers only the 5;
  - the held pool merges into ONE coarse block stay (verbatims preserved);
    supplement names attach to it as a group; stored status tracks the
    counter — names_pending | complete | over ('over' reachable at last);
  - mismatch never crashes: short -> pending stays positive; overfull ->
    overage advisory, completeness UNAFFECTED (§8.5.2);
  - the dispatch floor holds THROUGH supplements: a supplement's own junk
    and held rows survive on their own;
  - chains work: a supplement on a supplement re-points prior block guests
    onto the new block (the build-time addendum), depth-2 lineage keeps the
    delta honest.

Dev lists only; holdout sealed.
"""
import os
import sqlite3

from export import build_pms_csv
from maps import parse_park_stays, read_text_rows, TEXTMAIL_TXT, TEXTMAIL_MAP
from parser import transcribe_with_stays, ColumnMap, NameSlot
from stay import reconcile, completeness_status
from storage import (connect, init_db, save_list, load_guests_with_ids,
                     load_stays, record_pms_export, confirm_export, pms_delta,
                     export_coverage, apply_supplement)

DB = "/tmp/soglia_test_supplements.db"
# Mirrors textmail's real shape: name slots at columns 1/2; residue rows
# (held trailers, junk) live in column 0, OUTSIDE the slots.
_SUPP_MAP = ColumnMap(header_rows=0, default_role="20",
                      name_slots=[NameSlot(surname_column=1, firstname_column=2)])


def _supp(names):
    """A supplement file, parsed like any list (stage-2 on synthetic rows)."""
    return transcribe_with_stays([["", n, "X"] for n in names], _SUPP_MAP)


def _fresh(guests, stays):
    if os.path.exists(DB):
        os.remove(DB)
    c = connect(DB)
    init_db(c)
    vid = save_list(c, guests, hotel="Hotel Continentale",
                    source_filename="mon.txt", stays=stays)
    return c, vid


def _state(c, vid):
    guests = [g for _, g in load_guests_with_ids(c, vid)]
    stays = load_stays(c, vid)
    rec = reconcile(stays, guests)
    return guests, stays, rec


# --- THE FLAGSHIP: the whole Monday -> Wednesday story on real data ------------
def test_flagship_monday_to_wednesday():
    res = transcribe_with_stays(read_text_rows(TEXTMAIL_TXT), TEXTMAIL_MAP)
    c, v1 = _fresh(res.guests, res.stays)

    # MONDAY: export everything named, confirm. Commit 2's flagship state:
    ids = [gid for gid, _ in load_guests_with_ids(c, v1)]
    confirm_export(c, record_pms_export(c, v1, ids,
                                        build_pms_csv(res.guests, res.stays)))
    _, _, rec1 = _state(c, v1)
    assert export_coverage(c, v1) == "full"
    assert completeness_status(rec1) == "awaiting_completion" and rec1["pending"] == 2

    # TUESDAY: the email names the two drivers -> a supplement version
    v2 = apply_supplement(c, v1, _supp(["KOWALSKI Piotr", "NOWAK Jan"]),
                          source_filename="tue-email.txt")
    g2, s2, rec2 = _state(c, v2)
    assert len(g2) == 49
    assert rec2 == {"expected": 49, "named": 49, "pending": 0,
                    "overage": 0, "unrecognized": 0}, rec2
    assert completeness_status(rec2) == "complete", \
        "the block is filled: the list is finally COMPLETE"
    block = [s for s in s2 if s.source_row is None][0]
    assert (block.pax_expected, block.status, block.verbatim) == \
        (2, "complete", "+ 2 autisti"), "block: counter-derived status, verbatim kept"
    assert sum(1 for g in g2 if g.stay_id == block.stay_id) == 2

    # the 47 STAY exported through lineage; the delta offers EXACTLY the 2
    assert export_coverage(c, v2) == "partial"
    delta = pms_delta(c, v2)
    assert sorted(g.cognome for _, g in delta) == ["KOWALSKI Piotr", "NOWAK Jan"]

    # WEDNESDAY: export the delta, confirm -> both axes at their endpoints
    confirm_export(c, record_pms_export(c, v2, [gid for gid, _ in delta],
                                        build_pms_csv([g for _, g in delta], s2)))
    assert export_coverage(c, v2) == "full" and pms_delta(c, v2) == []
    c.close()
    print("PASS FLAGSHIP: Mon full/awaiting -> Tue supplement -> complete, "
          "delta = exactly the 2 -> Wed full/complete. Both axes end-to-end.")


# --- the stepfather numbers, literally ------------------------------------------
def test_stepfather_numbers():
    rows = [["", f"GUEST{i:02d}", "X"] for i in range(25)] + [["+ 5 pax", "", ""]]
    v1res = transcribe_with_stays(rows, _SUPP_MAP)
    assert len(v1res.guests) == 25 and sum(
        s.pax_expected for s in v1res.stays if s.status == "names_pending") == 5
    c, v1 = _fresh(v1res.guests, v1res.stays)
    ids = [gid for gid, _ in load_guests_with_ids(c, v1)]
    confirm_export(c, record_pms_export(c, v1, ids,
                                        build_pms_csv(v1res.guests, v1res.stays)))

    v2 = apply_supplement(c, v1, _supp([f"LATE{i}" for i in range(5)]),
                          source_filename="supp.txt")
    delta = pms_delta(c, v2)
    assert len(delta) == 5 and all(g.cognome.startswith("LATE") for _, g in delta), \
        "25 already in -> the next export offers ONLY the 5 (§8.5.4, verbatim)"
    assert export_coverage(c, v2) == "partial"
    _, _, rec = _state(c, v2)
    assert completeness_status(rec) == "complete" and rec["expected"] == 30
    c.close()
    print("PASS stepfather: 25 exported + 5 supplement -> delta is exactly the 5")


# --- short supplement, block provenance, prior untouched ------------------------
def test_short_supplement_and_immutability():
    res = parse_park_stays()
    c, v1 = _fresh(res.guests, res.stays)
    g1_before, s1_before, _ = _state(c, v1)

    v2 = apply_supplement(c, v1, _supp([f"S{i}" for i in range(5)]),
                          source_filename="supp.txt")
    g2, s2, rec = _state(c, v2)
    block = [s for s in s2 if s.source_row is None][0]
    assert (block.pax_expected, block.status) == (18, "names_pending")
    assert "Al.Mat. arrivi 18 pax" in block.verbatim \
        and "Al.Mat. arrivi 17 pax" in block.verbatim, \
        "distinct held texts survive the merge (§8.5.7)"
    assert rec["pending"] == 13 and completeness_status(rec) == "awaiting_completion"
    assert len([s for s in s2 if s.status == "complete"]) == 19, \
        "named stays carry forward untouched"
    # twins carried intact: a carried twin pair still shares its stay
    by_stay = {}
    for g in g2[:23]:
        by_stay.setdefault(g.stay_id, []).append(g)
    assert sorted(len(v) for v in by_stay.values()) == [1] * 15 + [2] * 4

    g1_after, s1_after, _ = _state(c, v1)
    assert g1_after == g1_before and s1_after == s1_before, \
        "the prior version is NEVER touched"
    c.close()
    print("PASS short supplement: 5 of 18 -> pending 13; block verbatims kept; "
          "prior version byte-untouched")


# --- overfull: 'over' reachable; completeness unaffected (§8.5.2) ---------------
def test_overfull_and_supplement_onto_complete():
    res = transcribe_with_stays(read_text_rows(TEXTMAIL_TXT), TEXTMAIL_MAP)
    c, v1 = _fresh(res.guests, res.stays)
    v2 = apply_supplement(c, v1, _supp(["A", "B", "C"]), source_filename="s1")
    _, s2, rec2 = _state(c, v2)
    block = [s for s in s2 if s.source_row is None][0]
    assert block.status == "over" and rec2["overage"] == 1
    assert rec2["pending"] == 0 and completeness_status(rec2) == "complete", \
        "overage is advisory — an extra named person is still registrable"

    # supplement onto an already-complete list: extras land on a 0-pax over
    # block; completeness stays complete, overage grows
    v3 = apply_supplement(c, v2, _supp(["EXTRA"]), source_filename="s2")
    _, s3, rec3 = _state(c, v3)
    assert rec3["overage"] == 2 and completeness_status(rec3) == "complete"
    assert any(s.status == "over" and s.pax_expected == 0 for s in s3)
    c.close()
    print("PASS overfull: 'over' reachable; overage advisory never blocks; "
          "supplement-onto-complete stays complete")


# --- chains: re-pointing + depth-2 lineage --------------------------------------
def test_chain_of_two_supplements():
    res = parse_park_stays()
    c, v1 = _fresh(res.guests, res.stays)
    ids = [gid for gid, _ in load_guests_with_ids(c, v1)]
    confirm_export(c, record_pms_export(c, v1, ids,
                                        build_pms_csv(res.guests, res.stays)))

    v2 = apply_supplement(c, v1, _supp([f"S{i}" for i in range(10)]),
                          source_filename="s1")
    v3 = apply_supplement(c, v2, _supp([f"T{i}" for i in range(8)]),
                          source_filename="s2")
    g3, s3, rec = _state(c, v3)
    block = [s for s in s3 if s.source_row is None][0]
    on_block = sum(1 for g in g3 if g.stay_id == block.stay_id)
    assert (on_block, block.pax_expected, block.status) == (18, 18, "complete"), \
        "prior supplement's names re-point onto the new block (build addendum)"
    assert rec == {"expected": 41, "named": 41, "pending": 0,
                   "overage": 0, "unrecognized": 0}
    assert completeness_status(rec) == "complete"
    # depth-2 lineage: only the 18 supplement names are un-exported
    delta = pms_delta(c, v3)
    assert len(delta) == 18 and all(
        g.cognome[0] in "ST" for _, g in delta), \
        "the original 23 stay exported through a depth-2 lineage chain"
    c.close()
    print("PASS chain of two: block 18/18 complete via re-pointing; "
          "delta honest through depth-2 lineage; park lands on 41/41/0")


# --- the floor survives supplements ---------------------------------------------
def test_floor_through_supplement():
    res = parse_park_stays()
    c, v1 = _fresh(res.guests, res.stays)
    # a supplement file with 2 names, a junk residue row, and its OWN held row
    supp = transcribe_with_stays(
        [["", "S0", "X"], ["", "S1", "X"],
         ["Totale: 47", "", ""], ["+ 3 autisti", "", ""]],
        _SUPP_MAP)
    v2 = apply_supplement(c, v1, supp, source_filename="messy-supp.txt")
    _, s2, rec = _state(c, v2)

    unrec = [s for s in s2 if s.status == "unrecognized"]
    assert len(unrec) == 1 and unrec[0].verbatim == "Totale: 47", \
        "junk in a supplement can no more vanish than junk in a roster"
    extra_held = [s for s in s2 if s.status == "names_pending"
                  and s.verbatim == "+ 3 autisti"]
    assert len(extra_held) == 1 and extra_held[0].pax_expected == 3, \
        "a supplement's own held row ADDS capacity, never merges into the block"
    assert rec["pending"] == (18 - 2) + 3 and rec["unrecognized"] == 1
    assert completeness_status(rec) == "awaiting_completion"
    c.close()
    print("PASS floor through supplement: unrecognized carried + blocks; "
          "supplement-held adds capacity separately")


# --- relation_to_prior + legacy migration ---------------------------------------
def test_relation_and_legacy_migration():
    res = parse_park_stays()
    c, v1 = _fresh(res.guests, res.stays)
    v2 = apply_supplement(c, v1, _supp(["S0"]), source_filename="s")
    rels = dict(c.execute("SELECT id, relation_to_prior FROM list_version"))
    assert rels[v1] == "initial" and rels[v2] == "supplement"
    c.close()

    # a commit-2-era database: submission tables present, NO lineage table,
    # NO relation_to_prior column -> init_db migrates in place
    os.remove(DB)
    legacy = sqlite3.connect(DB)
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
    init_db(c)
    vid = save_list(c, res.guests, hotel="x", source_filename="x",
                    stays=res.stays)
    ids = [gid for gid, _ in load_guests_with_ids(c, vid)]
    confirm_export(c, record_pms_export(c, vid, ids, "artifact"))
    v2 = apply_supplement(c, vid, _supp(["S0", "S1"]), source_filename="s")
    assert len(pms_delta(c, v2)) == 2 and export_coverage(c, v2) == "partial"
    c.close()
    os.remove(DB)
    print("PASS relation_to_prior round-trips; commit-2-era DB migrated "
          "in place (new table + new column), lineage delta works on it")


if __name__ == "__main__":
    test_flagship_monday_to_wednesday()
    test_stepfather_numbers()
    test_short_supplement_and_immutability()
    test_overfull_and_supplement_onto_complete()
    test_chain_of_two_supplements()
    test_floor_through_supplement()
    test_relation_and_legacy_migration()
    print("ALL GREEN")
