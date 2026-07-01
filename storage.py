"""
Soglia — persistence (the application's memory).

A single local SQLite file, soglia.db, is the database: no server, no network,
nothing in the cloud — `import sqlite3` is built into Python. This is what
carries a list across the gap where a human walks away (upload Monday, submit
Wednesday) instead of evaporating when a script ends.

Tables follow the §8 schema. The foreign keys (guest.list_version_id ->
list_version.id -> guest_list.id) are the relational links we sketched: a list
has versions, a version has guests.

Scope note: this persists the CORE guest data (the flat Guest) and, since the
STAY foundation (addendum §8.5.8 commit 1), the stay table + guest.stay_id
links. Per-field provenance (field_meta: verbatim / origin / tier) and the
Party table arrive together with the review UI — the UI is what reads
provenance, so they belong to the same step. Adding them is just more tables.
"""
import dataclasses
import datetime
import sqlite3

from stay import Stay
from tracciato import Guest

SCHEMA = """
CREATE TABLE IF NOT EXISTS guest_list (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    hotel       TEXT,
    created_at  TEXT
);
CREATE TABLE IF NOT EXISTS list_version (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    guest_list_id   INTEGER REFERENCES guest_list(id),
    source_filename TEXT,
    created_at      TEXT
);
CREATE TABLE IF NOT EXISTS guest (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    list_version_id  INTEGER REFERENCES list_version(id),
    idx              INTEGER,                 -- position within the list
    tipo_alloggiato  TEXT, cognome TEXT, nome TEXT, sesso TEXT,
    data_nascita     TEXT, born_in_italy INTEGER,
    comune_nascita   TEXT, provincia_nascita TEXT, stato_nascita TEXT,
    cittadinanza     TEXT, tipo_documento TEXT, numero_documento TEXT, luogo_rilascio TEXT,
    skip_flag        TEXT DEFAULT '',          -- review provenance: matched the map's skip rule
    stay_id          INTEGER                   -- joins stay.stay_id within the same version
);
CREATE TABLE IF NOT EXISTS stay (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    list_version_id  INTEGER REFERENCES list_version(id),
    stay_id          INTEGER,                  -- per-list id guests reference
    pax_expected     INTEGER,
    status           TEXT,                     -- names_pending | complete
    verbatim         TEXT,                     -- held rows: source cell text
    source_row       INTEGER                   -- 0-based row in the source table
);
"""

# the Guest fields we store, in one place so save/load can't drift apart
_GUEST_COLS = ["tipo_alloggiato", "cognome", "nome", "sesso", "data_nascita",
               "born_in_italy", "comune_nascita", "provincia_nascita",
               "stato_nascita", "cittadinanza", "tipo_documento",
               "numero_documento", "luogo_rilascio", "skip_flag", "stay_id"]

# the Stay fields we store, same one-place rule as _GUEST_COLS
_STAY_COLS = ["stay_id", "pax_expected", "status", "verbatim", "source_row"]

# Every Guest field must be persisted. A field added to Guest without a column
# here silently evaporates on the next save/load — exactly how skip_flag (review
# provenance, a RED) was once lost. Fail loudly at import instead.
assert set(_GUEST_COLS) == {f.name for f in dataclasses.fields(Guest)}, \
    "SCHEMA + _GUEST_COLS must cover every Guest field — update them together"
assert set(_STAY_COLS) == {f.name for f in dataclasses.fields(Stay)}, \
    "SCHEMA + _STAY_COLS must cover every Stay field — update them together"


def connect(path="soglia.db"):
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn):
    conn.executescript(SCHEMA)
    # Migration: skip_flag and stay_id arrived after the first release, and
    # CREATE TABLE IF NOT EXISTS won't touch an existing guest table — so
    # upgrade an old soglia.db in place rather than crash on the next save.
    # (The stay table itself is handled by CREATE TABLE IF NOT EXISTS above.)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(guest)")]
    for col, ddl in (("skip_flag", "TEXT DEFAULT ''"), ("stay_id", "INTEGER")):
        if col not in cols:
            conn.execute(f"ALTER TABLE guest ADD COLUMN {col} {ddl}")
    conn.commit()


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def save_list(conn, guests, *, hotel, source_filename, stays=None):
    """Persist a parsed list as a new version (guests + their stays, if any).
    Returns the list_version id."""
    cur = conn.cursor()
    cur.execute("INSERT INTO guest_list (hotel, created_at) VALUES (?, ?)", (hotel, _now()))
    gl_id = cur.lastrowid
    cur.execute("INSERT INTO list_version (guest_list_id, source_filename, created_at) "
                "VALUES (?, ?, ?)", (gl_id, source_filename, _now()))
    lv_id = cur.lastrowid

    cols = ["list_version_id", "idx"] + _GUEST_COLS
    placeholders = ", ".join("?" * len(cols))
    sql = f"INSERT INTO guest ({', '.join(cols)}) VALUES ({placeholders})"
    for i, g in enumerate(guests):
        vals = [lv_id, i]
        for c in _GUEST_COLS:
            v = getattr(g, c)
            vals.append(int(v) if c == "born_in_italy" else v)
        cur.execute(sql, vals)

    if stays:
        s_cols = ["list_version_id"] + _STAY_COLS
        s_sql = (f"INSERT INTO stay ({', '.join(s_cols)}) "
                 f"VALUES ({', '.join('?' * len(s_cols))})")
        for s in stays:
            cur.execute(s_sql, [lv_id] + [getattr(s, c) for c in _STAY_COLS])

    conn.commit()
    return lv_id


def load_stays(conn, list_version_id):
    """Rebuild the Stay objects for a saved version (ordered by stay_id)."""
    sql = (f"SELECT {', '.join(_STAY_COLS)} FROM stay "
           f"WHERE list_version_id = ? ORDER BY stay_id")
    return [Stay(**dict(zip(_STAY_COLS, row)))
            for row in conn.execute(sql, (list_version_id,)).fetchall()]


def load_list(conn, list_version_id):
    """Rebuild the Guest objects for a saved version."""
    sql = f"SELECT {', '.join(_GUEST_COLS)} FROM guest WHERE list_version_id = ? ORDER BY idx"
    out = []
    for row in conn.execute(sql, (list_version_id,)).fetchall():
        kw = dict(zip(_GUEST_COLS, row))
        kw["born_in_italy"] = bool(kw["born_in_italy"])
        out.append(Guest(**kw))
    return out


def list_versions(conn):
    """Every saved version: (version_id, hotel, source_filename, when, guest_count)."""
    return conn.execute("""
        SELECT lv.id, gl.hotel, lv.source_filename, lv.created_at, COUNT(g.id)
        FROM list_version lv
        JOIN guest_list gl ON gl.id = lv.guest_list_id
        LEFT JOIN guest g ON g.list_version_id = lv.id
        GROUP BY lv.id ORDER BY lv.id
    """).fetchall()
