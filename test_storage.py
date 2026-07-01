"""
Tests for persistence. No pytest:
    python3 test_storage.py

The proof: save a list, CLOSE the connection, re-open a FRESH one (simulating a
later session), load the list back — and it must be byte-identical. That round
trip through a re-opened file is what "the data survives" actually means.

Regressions guarded here:
  - skip_flag is review provenance (it drives the "confermare che non sia un
    ospite reale" RED) and must survive the database. A flag that evaporates
    between upload-Monday and submit-Wednesday would let a wrongly-skipped
    real guest go clean silently. The POLISH list (7 flagged header/legend
    rows) is the fixture — park's Al.Mat rows are held STAYS now, not flagged
    guests, and MIX18 has no skip rule.
  - stays + stay_id links must survive too: park's 23 guests on their stays
    plus 9 held names_pending stays reload intact, so reconciliation (§8.5.2)
    computes the same 41/23/18 after a restart as before it.
"""
import os
import sqlite3

from storage import connect, init_db, save_list, load_list, load_stays, list_versions
from maps import parse_mix18, parse_polish, parse_park_stays
from stay import reconcile

DB = "/tmp/soglia_test.db"

# The guest table as it existed BEFORE skip_flag — for the migration check.
_LEGACY_SCHEMA = """
CREATE TABLE guest_list (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    hotel       TEXT,
    created_at  TEXT
);
CREATE TABLE list_version (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    guest_list_id   INTEGER REFERENCES guest_list(id),
    source_filename TEXT,
    created_at      TEXT
);
CREATE TABLE guest (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    list_version_id  INTEGER REFERENCES list_version(id),
    idx              INTEGER,
    tipo_alloggiato  TEXT, cognome TEXT, nome TEXT, sesso TEXT,
    data_nascita     TEXT, born_in_italy INTEGER,
    comune_nascita   TEXT, provincia_nascita TEXT, stato_nascita TEXT,
    cittadinanza     TEXT, tipo_documento TEXT, numero_documento TEXT, luogo_rilascio TEXT
);
"""


def main():
    if os.path.exists(DB):
        os.remove(DB)

    original = parse_mix18()
    assert len(original) == 39

    # save, then fully close the connection
    c = connect(DB)
    init_db(c)
    vid = save_list(c, original, hotel="Park Hotel Salice Terme", source_filename="MIX18.docx")
    c.close()

    # re-open a brand-new connection to the same file — the original .docx is NOT touched
    c2 = connect(DB)
    loaded = load_list(c2, vid)
    assert loaded == original, "round trip must preserve the guests exactly"

    # a second save creates a second version, both coexist
    save_list(c2, original[:3], hotel="Park Hotel Salice Terme", source_filename="correction.docx")
    versions = list_versions(c2)
    assert len(versions) == 2 and versions[0][4] == 39 and versions[1][4] == 3

    # REGRESSION — skip_flag survives the round trip. Dataclass equality below
    # compares skip_flag too, so losing the flag cannot pass quietly.
    polish = parse_polish()
    assert sum(1 for g in polish if g.skip_flag) == 7, "fixture drift: expected 7 flagged rows"
    pvid = save_list(c2, polish, hotel="Park Hotel Salice Terme", source_filename="polish.xlsx")
    c2.close()

    c3 = connect(DB)
    polish_back = load_list(c3, pvid)
    assert polish_back == polish, "round trip must preserve skip_flag too"
    assert sum(1 for g in polish_back if g.skip_flag) == 7

    # REGRESSION — stays + stay_id links survive: reconciliation must compute
    # the same §13.4 arithmetic (41/23/18) from the reloaded data.
    park = parse_park_stays()
    svid = save_list(c3, park.guests, hotel="Park Hotel Salice Terme",
                     source_filename="park.xlsx", stays=park.stays)
    c3.close()

    c3b = connect(DB)
    g_back, s_back = load_list(c3b, svid), load_stays(c3b, svid)
    c3b.close()
    assert g_back == park.guests and s_back == park.stays, \
        "stays / stay_id links must survive the round trip"
    rec = reconcile(s_back, g_back)
    assert (rec["expected"], rec["named"], rec["pending"]) == (41, 23, 18)

    # MIGRATION — a soglia.db created before skip_flag/stay_id/stay existed
    # must be upgraded in place by init_db, not crash on the next save.
    os.remove(DB)
    legacy = sqlite3.connect(DB)
    legacy.executescript(_LEGACY_SCHEMA)
    legacy.close()
    c4 = connect(DB)
    init_db(c4)
    mvid = save_list(c4, park.guests, hotel="Park Hotel Salice Terme",
                     source_filename="park.xlsx", stays=park.stays)
    migrated_g, migrated_s = load_list(c4, mvid), load_stays(c4, mvid)
    c4.close()
    assert migrated_g == park.guests and migrated_s == park.stays, \
        "migrated legacy database must round-trip stays and both new guest columns"

    os.remove(DB)
    print("\u2713 PASS \u2014 persistence works.")
    print("        39 guests saved, connection closed, re-opened from the file, loaded back IDENTICAL;")
    print("        multiple versions coexist with correct counts (39 and 3);")
    print("        skip_flag survives the round trip (polish: 7 flagged rows intact after reload);")
    print("        stays + stay_id links survive (park reloads to the same 41/23/18 reconciliation);")
    print("        a pre-skip_flag/pre-stay database is migrated in place by init_db.")


if __name__ == "__main__":
    main()
