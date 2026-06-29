"""
Tests for persistence. No pytest:
    python3 test_storage.py

The proof: save a list, CLOSE the connection, re-open a FRESH one (simulating a
later session), load the list back — and it must be byte-identical. That round
trip through a re-opened file is what "the data survives" actually means.
"""
import os

from storage import connect, init_db, save_list, load_list, list_versions
from maps import parse_mix18

DB = "/tmp/soglia_test.db"


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
    c2.close()

    os.remove(DB)
    print("\u2713 PASS \u2014 persistence works.")
    print("        39 guests saved, connection closed, re-opened from the file, loaded back IDENTICAL;")
    print("        multiple versions coexist with correct counts (39 and 3).")


if __name__ == "__main__":
    main()
