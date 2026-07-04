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

from export import Submission, SubmissionResult
import json

from stay import Stay, derive_status, reconcile, completeness_status
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
CREATE TABLE IF NOT EXISTS submission (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    list_version_id        INTEGER REFERENCES list_version(id),
    target                 TEXT,               -- alloggiati | pms (§8.5.4)
    idempotency_key        TEXT UNIQUE,        -- §13.9: double-click guard
    status                 TEXT,               -- pms: generated | export_confirmed | superseded
    submitted_arrival_date TEXT,               -- §13.2: stamped at submission
    artifact_hash          TEXT,               -- sha256 of the handed-over bytes
    submitted_at           TEXT,
    export_confirm         TEXT DEFAULT ''     -- §8.5.5 audit json, written at confirm
);
CREATE TABLE IF NOT EXISTS submission_result (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    submission_id  INTEGER REFERENCES submission(id),
    guest_id       INTEGER REFERENCES guest(id),
    outcome        TEXT,                       -- "" manifest -> exported_unverified at confirm
    portal_line_no INTEGER,                    -- alloggiati verdict loop — stubbed
    portal_reason  TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS guest_lineage (
    guest_id        INTEGER PRIMARY KEY REFERENCES guest(id),
    prior_guest_id  INTEGER REFERENCES guest(id)
    -- a receipt of OUR OWN supplement carry-forward (deterministic copy,
    -- §8.5.3) — NOT the stubbed person_key (fuzzy match of independent
    -- uploads). Export facts survive the carry through this chain (§8.5.4).
);
CREATE TABLE IF NOT EXISTS stay (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    list_version_id  INTEGER REFERENCES list_version(id),
    stay_id          INTEGER,                  -- per-list id guests reference
    pax_expected     INTEGER,
    status           TEXT,                     -- names_pending | complete | over | unrecognized
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

# Submission mirrors its storage PK as `id` (results reference it; confirm
# takes it) — inserted as NULL so SQLite autoincrements, selected back real.
_SUB_COLS = ["id", "list_version_id", "target", "idempotency_key", "status",
             "submitted_arrival_date", "artifact_hash", "submitted_at",
             "export_confirm"]
_RES_COLS = ["submission_id", "guest_id", "outcome", "portal_line_no",
             "portal_reason"]

# Every Guest field must be persisted. A field added to Guest without a column
# here silently evaporates on the next save/load — exactly how skip_flag (review
# provenance, a RED) was once lost. Fail loudly at import instead.
assert set(_GUEST_COLS) == {f.name for f in dataclasses.fields(Guest)}, \
    "SCHEMA + _GUEST_COLS must cover every Guest field — update them together"
assert set(_STAY_COLS) == {f.name for f in dataclasses.fields(Stay)}, \
    "SCHEMA + _STAY_COLS must cover every Stay field — update them together"
assert set(_SUB_COLS) == {f.name for f in dataclasses.fields(Submission)}, \
    "SCHEMA + _SUB_COLS must cover every Submission field — update them together"
assert set(_RES_COLS) == {f.name for f in dataclasses.fields(SubmissionResult)}, \
    "SCHEMA + _RES_COLS must cover every SubmissionResult field — update them together"


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
    lv_cols = [r[1] for r in conn.execute("PRAGMA table_info(list_version)")]
    if "relation_to_prior" not in lv_cols:
        # §13.4 / §8.5.3: initial | correction | supplement ('' = pre-3 rows)
        conn.execute("ALTER TABLE list_version ADD COLUMN "
                     "relation_to_prior TEXT DEFAULT ''")
    if "completeness_override" not in lv_cols:
        # §8.5.5: the mark-complete assertion json (empty = never overridden)
        conn.execute("ALTER TABLE list_version ADD COLUMN "
                     "completeness_override TEXT DEFAULT ''")
    conn.commit()


def save_list(conn, guests, *, hotel, source_filename, stays=None):
    """Persist a parsed list as a new version (guests + their stays, if any).
    Returns the list_version id."""
    cur = conn.cursor()
    cur.execute("INSERT INTO guest_list (hotel, created_at) VALUES (?, ?)", (hotel, _now()))
    gl_id = cur.lastrowid
    cur.execute("INSERT INTO list_version (guest_list_id, source_filename, "
                "created_at, relation_to_prior) VALUES (?, ?, ?, 'initial')",
                (gl_id, source_filename, _now()))
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


# --- export-state tracking + delta export (addendum §8.5.4; commit 2) ----------
# The two axes deliberately live in different places: completeness is a
# property of the PARSE (orchestrator.ListResult.completeness()); export
# coverage is a property of the RECORD (these functions, over persisted
# hand-off facts). Artifact TEXT is injected by the caller (export.py builds
# the canonical CSV; a Bedzzle-shaped builder slots in later, zero change here).

def _sha256(text):
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now():
    # UTC, ISO — the one timestamp everything stored here uses
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def load_guests_with_ids(conn, list_version_id):
    """[(guest_id, Guest)] in list order — the identity the delta runs on
    (within-version guest.id; person_key cross-version diff is stubbed)."""
    sql = (f"SELECT id, {', '.join(_GUEST_COLS)} FROM guest "
           f"WHERE list_version_id = ? ORDER BY idx")
    out = []
    for row in conn.execute(sql, (list_version_id,)).fetchall():
        kw = dict(zip(_GUEST_COLS, row[1:]))
        kw["born_in_italy"] = bool(kw["born_in_italy"])
        out.append((row[0], Guest(**kw)))
    return out


def _insert_submission(conn, *, list_version_id, target, key, status,
                       arrival_date, artifact_text):
    cur = conn.cursor()
    cols = _SUB_COLS  # id inserted as NULL -> autoincrement
    cur.execute(f"INSERT INTO submission ({', '.join(cols)}) "
                f"VALUES ({', '.join('?' * len(cols))})",
                [None, list_version_id, target, key, status, arrival_date,
                 _sha256(artifact_text), _now(), ""])
    return cur.lastrowid


def record_pms_export(conn, list_version_id, guest_ids, artifact_text):
    """Generation step (§8.5.4): appends a SUBMISSION(target=pms,
    status=generated) + its MANIFEST (result rows, outcome="") for exactly
    `guest_ids` — the set the artifact was built from. Idempotent: the same
    (version, guest set, bytes) returns the existing submission id instead of
    recording twice (§13.9). Appending a genuinely new export marks the prior
    pms export `superseded` (doc-literal); results already written keep their
    force — superseded means no-longer-the-newest, never invalidated."""
    ids = sorted(set(guest_ids))
    base = _sha256(f"{list_version_id}|pms|{','.join(map(str, ids))}|"
                   f"{_sha256(artifact_text)}")
    # §13.9's guard is for DOUBLE-CLICKS: a collision with a LIVE submission
    # returns it. A collision with a SUPERSEDED one is a regeneration after an
    # intervening export (commit-2 review finding) — a new intent that happens
    # to produce old bytes — so a fresh submission is minted under a suffixed
    # key: the regeneration lineage stays auditable in the key itself.
    key, n = base, 1
    while True:
        row = conn.execute("SELECT id, status FROM submission "
                           "WHERE idempotency_key = ?", (key,)).fetchone()
        if row is None:
            break                           # free key -> record under it
        if row[1] != "superseded":
            return row[0]                   # true double-click: once
        n += 1
        key = f"{base}|r{n}"

    conn.execute("UPDATE submission SET status = 'superseded' "
                 "WHERE list_version_id = ? AND target = 'pms' "
                 "AND status != 'superseded'", (list_version_id,))
    sid = _insert_submission(conn, list_version_id=list_version_id,
                             target="pms", key=key, status="generated",
                             arrival_date="", artifact_text=artifact_text)
    cur = conn.cursor()
    for gid in ids:
        cur.execute(f"INSERT INTO submission_result ({', '.join(_RES_COLS)}) "
                    f"VALUES ({', '.join('?' * len(_RES_COLS))})",
                    [sid, gid, "", None, ""])
    conn.commit()
    return sid


def confirm_export(conn, submission_id, *, actor):
    """generated -> export_confirmed: the human asserts "the file imported."
    Upgrades this submission's manifest to outcome=exported_unverified — the
    write that flips guests to exported (coverage reads outcomes only) — and
    records the §8.5.5 assertion {actor, ts, guest_count}: a belief that can
    be wrong, so we log WHOSE belief and WHEN (the honest ceiling without a
    PMS API). `actor` is required: an unattributed audit record is hollow.
    REFUSED for a superseded submission: a newer file exists, and confirming
    stale bytes would record a belief about a file the human probably didn't
    import."""
    row = conn.execute("SELECT target, status FROM submission WHERE id = ?",
                       (submission_id,)).fetchone()
    if row is None:
        raise ValueError(f"no submission {submission_id}")
    target, status = row
    if target != "pms" or status != "generated":
        raise ValueError(f"confirm_export needs a pms submission in "
                         f"'generated', got target={target!r} status={status!r}")
    conn.execute("UPDATE submission_result SET outcome = 'exported_unverified' "
                 "WHERE submission_id = ?", (submission_id,))
    guest_count = conn.execute(
        "SELECT COUNT(*) FROM submission_result WHERE submission_id = ?",
        (submission_id,)).fetchone()[0]
    record = json.dumps({"actor": actor, "ts": _now(),
                         "guest_count": guest_count}, sort_keys=True)
    conn.execute("UPDATE submission SET status = 'export_confirmed', "
                 "export_confirm = ? WHERE id = ?", (record, submission_id))
    conn.commit()


def record_alloggiati_submission(conn, list_version_id, artifact_text,
                                 arrival_date):
    """Minimal alloggiati hand-off record (status=pending): keeps every
    hand-off in one place and stamps §13.2's submit-time arrival date. The
    portal verdict/receipt loop is stubbed (§8.5.8) — no result rows here."""
    key = _sha256(f"{list_version_id}|alloggiati|{arrival_date}|"
                  f"{_sha256(artifact_text)}")
    row = conn.execute("SELECT id FROM submission WHERE idempotency_key = ?",
                       (key,)).fetchone()
    if row:
        return row[0]
    sid = _insert_submission(conn, list_version_id=list_version_id,
                             target="alloggiati", key=key, status="pending",
                             arrival_date=arrival_date,
                             artifact_text=artifact_text)
    conn.commit()
    return sid


def _exported_guest_ids(conn, list_version_id):
    """Guests of this version with a confirmed pms result — ANCESTOR-AWARE:
    a carried guest inherits its lineage chain's results (the chain is a
    receipt of our own supplement copy, exact by construction; NOT the
    stubbed person_key). The confirmed set spans versions on purpose: an
    ancestor's result lives on the prior version's submission."""
    confirmed = {r[0] for r in conn.execute(
        "SELECT DISTINCT r.guest_id FROM submission_result r "
        "JOIN submission s ON s.id = r.submission_id "
        "WHERE s.target = 'pms' AND r.outcome = 'exported_unverified'")}
    lineage = dict(conn.execute(
        "SELECT guest_id, prior_guest_id FROM guest_lineage"))
    out = set()
    for gid, _ in load_guests_with_ids(conn, list_version_id):
        cur, seen = gid, set()
        while cur is not None and cur not in seen:
            if cur in confirmed:
                out.add(gid)
                break
            seen.add(cur)
            cur = lineage.get(cur)
    return out


def pms_delta(conn, list_version_id):
    """The §8.5.4 default guest set for a new export: persisted guests of the
    version WITHOUT a confirmed pms result — pure set membership. Includes
    red/flagged guests on purpose (plan call 5 + §6a: excluding them silently
    would drop a wrongly-skipped REAL person from the hand-off; junk in the
    delta fails LOUD and review-resolution will shrink the denominator)."""
    done = _exported_guest_ids(conn, list_version_id)
    return [(gid, g) for gid, g in load_guests_with_ids(conn, list_version_id)
            if gid not in done]


def export_coverage(conn, list_version_id):
    """§8.5.1 export axis, computed: none | partial | full over the version's
    guests, from confirmed results only. An empty version is 'none' — there
    is nothing to have covered."""
    all_ids = {gid for gid, _ in load_guests_with_ids(conn, list_version_id)}
    if not all_ids:
        return "none"
    done = _exported_guest_ids(conn, list_version_id) & all_ids
    if not done:
        return "none"
    return "full" if done == all_ids else "partial"


def load_submissions(conn, list_version_id):
    """All hand-offs for a version, oldest first — the audit trail."""
    sql = (f"SELECT {', '.join(_SUB_COLS)} FROM submission "
           f"WHERE list_version_id = ? ORDER BY id")
    return [Submission(**dict(zip(_SUB_COLS, row)))
            for row in conn.execute(sql, (list_version_id,)).fetchall()]


def load_results(conn, submission_id):
    """The per-guest lines of one submission (manifest or confirmed)."""
    sql = (f"SELECT {', '.join(_RES_COLS)} FROM submission_result "
           f"WHERE submission_id = ? ORDER BY guest_id")
    return [SubmissionResult(**dict(zip(_RES_COLS, row)))
            for row in conn.execute(sql, (submission_id,)).fetchall()]


# --- supplement accumulation (addendum §8.5.3; commit 3) ------------------------

def apply_supplement(conn, prior_version_id, supplement, *, source_filename):
    """§8.5.3: a supplement is a NEW version (relation_to_prior='supplement')
    carrying the prior version's guests forward and attaching the newly named
    ones to ONE coarse block stay — slot-binding deferred to a counter.

    Which list a supplement belongs to is the CALLER's statement (a UI
    selection, never an inference): `prior_version_id` says it.

    - Carried guests get fresh rows; guest_lineage records new -> old — a
      receipt of our own deterministic copy, so export facts survive the
      carry (§8.5.4's stepfather: the 25 stay exported, the delta offers 5).
    - The prior version's held stays MERGE into one block stay: pax_expected
      = their sum, verbatim = their distinct texts joined (§8.5.7 provenance
      preserved), status derived from the counter — 'over' becomes reachable
      here. Named/complete and unrecognized stays carry forward unchanged.
    - Supplement guests attach to the block (their own parse-side named
      stays are dropped: the block is the unit). The supplement file's
      NON-guest rows survive on their own: its held rows ADD capacity as
      separate stays; its unrecognized rows carry as-is — the dispatch
      floor holds through supplements.
    - The prior version is never touched. Returns the new version id."""
    row = conn.execute("SELECT guest_list_id FROM list_version WHERE id = ?",
                       (prior_version_id,)).fetchone()
    if row is None:
        raise ValueError(f"no list_version {prior_version_id}")
    gl_id = row[0]

    prior_pairs = load_guests_with_ids(conn, prior_version_id)
    prior_stays = load_stays(conn, prior_version_id)
    held = [s for s in prior_stays if s.status == "names_pending"]
    kept = [s for s in prior_stays if s.status != "names_pending"]
    new_guests = list(supplement.guests)
    supp_extra = [s for s in supplement.stays
                  if s.status in ("names_pending", "unrecognized")]

    next_sid = max([s.stay_id for s in prior_stays], default=0) + 1
    held_ids = {s.stay_id for s in held}
    # names a PREVIOUS supplement attached to the previous block are carried
    # onto the new block too — they count toward its stored status
    carried_onto_block = sum(1 for _, g in prior_pairs if g.stay_id in held_ids)
    block = None
    if held or new_guests:
        block_pax = sum(s.pax_expected for s in held)
        block = Stay(stay_id=next_sid,
                     pax_expected=block_pax,
                     status=derive_status(block_pax,
                                          carried_onto_block + len(new_guests)),
                     verbatim=" | ".join(dict.fromkeys(
                         s.verbatim for s in held if s.verbatim)),
                     source_row=None)   # a block spans rows; per-row texts kept above
        next_sid += 1
    remapped = []
    for s in supp_extra:
        remapped.append(dataclasses.replace(s, stay_id=next_sid))
        next_sid += 1

    cur = conn.cursor()
    cur.execute("INSERT INTO list_version (guest_list_id, source_filename, "
                "created_at, relation_to_prior) VALUES (?, ?, ?, 'supplement')",
                (gl_id, source_filename, _now()))
    new_vid = cur.lastrowid

    g_cols = ["list_version_id", "idx"] + _GUEST_COLS
    g_sql = (f"INSERT INTO guest ({', '.join(g_cols)}) "
             f"VALUES ({', '.join('?' * len(g_cols))})")

    def _gvals(g):
        return [int(v) if c == "born_in_italy" else v
                for c, v in ((c, getattr(g, c)) for c in _GUEST_COLS)]

    idx = 0
    for old_id, g in prior_pairs:                      # carried, verbatim
        if block is not None and g.stay_id in held_ids:
            # a guest attached to a merged held stay (a PREVIOUS supplement's
            # block) moves to the new block — otherwise a chain of
            # supplements orphans them and pending silently corrupts
            g = dataclasses.replace(g, stay_id=block.stay_id)
        cur.execute(g_sql, [new_vid, idx] + _gvals(g))
        cur.execute("INSERT INTO guest_lineage (guest_id, prior_guest_id) "
                    "VALUES (?, ?)", (cur.lastrowid, old_id))
        idx += 1
    for g in new_guests:                               # attach to the block
        cur.execute(g_sql, [new_vid, idx]
                    + _gvals(dataclasses.replace(g, stay_id=block.stay_id)))
        idx += 1

    s_cols = ["list_version_id"] + _STAY_COLS
    s_sql = (f"INSERT INTO stay ({', '.join(s_cols)}) "
             f"VALUES ({', '.join('?' * len(s_cols))})")
    for s in kept + ([block] if block else []) + remapped:
        cur.execute(s_sql, [new_vid] + [getattr(s, c) for c in _STAY_COLS])

    conn.commit()
    return new_vid


# --- the two audited human assertions (addendum §8.5.5; commit 4) ---------------

def mark_complete_override(conn, list_version_id, *, actor, reason):
    """§8.5.5: "machine flagged X, human took responsibility on this date" —
    the §13.7 philosophy above field level. Writes {actor, ts,
    pending_at_override, unrecognized_at_override, reason} onto the version
    (sorted-key json; unrecognized_at_override extends the spec'd shape —
    the dispatch floor postdates §8.5.5, and vouching past an unrecognized
    row must say so). REFUSED when there is nothing to vouch for (the
    version is genuinely complete) or when it is already vouched (the first
    record stands; a supplement makes a NEW version — new facts, new
    responsibility). Returns the record dict. The record — not the UI
    warning in front of it — is the point."""
    row = conn.execute("SELECT completeness_override FROM list_version "
                       "WHERE id = ?", (list_version_id,)).fetchone()
    if row is None:
        raise ValueError(f"no list_version {list_version_id}")
    if row[0]:
        raise ValueError("already complete_by_override — the first record "
                         "stands (a supplement creates a NEW version to assert)")
    rec = reconcile(load_stays(conn, list_version_id),
                    load_list(conn, list_version_id))
    if completeness_status(rec) == "complete":
        raise ValueError("version is genuinely complete — nothing to override")
    record = {"actor": actor, "ts": _now(),
              "pending_at_override": rec["pending"],
              "unrecognized_at_override": rec["unrecognized"],
              "reason": reason}
    conn.execute("UPDATE list_version SET completeness_override = ? "
                 "WHERE id = ?",
                 (json.dumps(record, sort_keys=True), list_version_id))
    conn.commit()
    return record


def version_completeness(conn, list_version_id):
    """The persisted-side twin of orchestrator.ListResult.completeness():
    §8.5.2 reconciliation + the §8.5.1 status INCLUDING complete_by_override,
    read off the stored version. This is what a UI calls."""
    row = conn.execute("SELECT completeness_override FROM list_version "
                       "WHERE id = ?", (list_version_id,)).fetchone()
    if row is None:
        raise ValueError(f"no list_version {list_version_id}")
    rec = reconcile(load_stays(conn, list_version_id),
                    load_list(conn, list_version_id))
    rec["status"] = completeness_status(rec, override=bool(row[0]))
    return rec
