"""
Tests for persistence. No pytest:
    python3 test_storage.py

The proof: save a list, CLOSE the connection, re-open a FRESH one (simulating a
later session), load the list back — and it must be byte-identical. That round
trip through a re-opened file is what "the data survives" actually means.

Regression guarded here: skip_flag is review provenance (it drives the
"confermare che non sia un ospite reale" RED) and must survive the database. A
flag that evaporates between upload-Monday and submit-Wednesday would let a
wrongly-skipped real guest go clean silently — the exact failure the flag
exists to prevent. The Park list (9 held "Al.Mat" rows) is the fixture that
proves it; MIX18 alone cannot, because it has no skip rule.
"""
import os
import sqlite3

from storage import connect, init_db, save_list, load_list, list_versions
from maps import parse_mix18, parse_park

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
    park = parse_park()
    assert sum(1 for g in park if g.skip_flag) == 9, "fixture drift: expected 9 held rows"
    pvid = save_list(c2, park, hotel="Park Hotel Salice Terme", source_filename="park.xlsx")
    c2.close()

    c3 = connect(DB)
    park_back = load_list(c3, pvid)
    c3.close()
    assert park_back == park, "round trip must preserve skip_flag too"
    assert sum(1 for g in park_back if g.skip_flag) == 9

    # MIGRATION — a soglia.db created before skip_flag existed must be upgraded
    # in place by init_db (ALTER TABLE), not crash on the next save.
    os.remove(DB)
    legacy = sqlite3.connect(DB)
    legacy.executescript(_LEGACY_SCHEMA)
    legacy.close()
    c4 = connect(DB)
    init_db(c4)
    mvid = save_list(c4, park, hotel="Park Hotel Salice Terme", source_filename="park.xlsx")
    migrated = load_list(c4, mvid)
    c4.close()
    assert migrated == park, "migrated legacy database must round-trip skip_flag"

    os.remove(DB)
    print("\u2713 PASS \u2014 persistence works.")
    print("        39 guests saved, connection closed, re-opened from the file, loaded back IDENTICAL;")
    print("        multiple versions coexist with correct counts (39 and 3);")
    print("        skip_flag survives the round trip (Park list: 9 held rows still flagged after reload);")
    print("        a pre-skip_flag database is migrated in place by init_db.")


if __name__ == "__main__":
    main()
