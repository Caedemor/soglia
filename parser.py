"""
Soglia — generalized stage-2 parser (map-driven transcription).

STAGE 1 understanding (which column is which) -> a ColumnMap.   [LLM, later]
STAGE 2 transcription (follow the map, build Guests) -> here.   [THIS FILE]

Grown to handle the variety in three real lists:
  - one OR two (or more) people per row, via name_slots;
  - a combined "SURNAME Firstname" cell OR separate surname/first-name columns;
  - truly blank rows yield nothing; held placeholder rows become
    names_pending Stays (stay.py) BEFORE any map skip rule applies; rows with
    content the map cannot see AT ALL become `unrecognized` Stays that block
    completeness (the floor — PLAN-dispatch-floor.md); a map may also supply
    a skip_row hint (emit-and-flag, never drop);
  - field cleaning is format-only (e.g. 05.12.1984 -> 05/12/1984), never meaning.
Anything not mapped is left empty so the validator surfaces it. What stage 2
CANNOT do (e.g. recognise that "GUIDE NOWAK" hides a role marker) is left for
stage 1 / review.
"""
from dataclasses import dataclass, field
from typing import Callable, Optional

from tracciato import Guest
from stay import Stay, held_pax

# ---- normalizers: tiny, format-only transforms a map can request -----------

def norm_passthrough(v: str) -> str:
    return v.strip()

def norm_dotted_date(v: str) -> str:
    """'05.12.1984' / '5.12.1984' / '05-12-1984' -> '05/12/1984'; '' -> ''. Format only."""
    v = v.strip()
    if not v:
        return ""
    for sep in (".", "/", "-"):
        if sep in v:
            parts = [p for p in v.split(sep) if p != ""]
            if len(parts) == 3:
                d, m, y = parts
                if len(y) == 2:
                    # A 2-digit year is AMBIGUOUS for a date of birth ("85"
                    # is almost certainly 1985, "12" almost certainly 2012)
                    # and this file NEVER invents: leave the value verbatim,
                    # the validator reds the format, a human decides.
                    return v
                return f"{int(d):02d}/{int(m):02d}/{y}"
    return v   # leave anything unexpected untouched; validation will judge it

def norm_doc_type_passport(v: str) -> str:
    """A passport-number column also tells us the document TYPE: passport when present."""
    return "PASOR" if v.strip() else ""

NORMALIZERS = {
    "passthrough": norm_passthrough,
    "dotted_date": norm_dotted_date,
    "doc_type_passport": norm_doc_type_passport,
}


# ---- the map: stage-1's output, this module's input ------------------------

@dataclass
class FieldRule:
    """How to fill ONE canonical field from the source row."""
    column: Optional[int] = None        # source column index; None = not present
    normalizer: str = "passthrough"
    const: Optional[str] = None         # fixed value for every row


@dataclass
class NameSlot:
    """How to read ONE person's name from a row. A row yields a guest per filled slot."""
    combined_column: Optional[int] = None     # a "SURNAME Firstname" cell
    name_order: str = "surname_first"         # or "first_surname"
    surname_column: Optional[int] = None      # OR separate columns
    firstname_column: Optional[int] = None

    def extract(self, row: list):
        """Return (surname, nome), or ('', '') if this slot is empty in this row."""
        def cell(i):
            return row[i] if (i is not None and i < len(row)) else ""
        if self.combined_column is not None:
            full = cell(self.combined_column).strip()
            if not full:
                return "", ""
            toks = full.split()
            if len(toks) <= 1:
                return full, ""
            if self.name_order == "first_surname":
                return toks[-1], " ".join(toks[:-1])
            return toks[0], " ".join(toks[1:])
        s, f = cell(self.surname_column).strip(), cell(self.firstname_column).strip()
        return (s, f) if (s or f) else ("", "")


@dataclass
class ColumnMap:
    """A complete description of one list's layout. Stage 1 produces this; stage 2 consumes it."""
    header_rows: int = 1
    name_slots: list = field(default_factory=list)        # list[NameSlot] — 1+ people per row
    fields: dict = field(default_factory=dict)            # canonical field -> FieldRule
    role_rule: Optional[Callable[[list], str]] = None     # row -> tipo_alloggiato code
    default_role: str = "20"                              # membro gruppo
    skip_row: Optional[Callable[[list], bool]] = None     # e.g. held "names pending" rows
    skip_desc: str = ""                                   # human-readable skip rule, for the review flag


def _value(row: list, rule: FieldRule) -> str:
    if rule.const is not None:
        return rule.const
    if rule.column is None or rule.column >= len(row):
        return ""
    return NORMALIZERS[rule.normalizer](row[rule.column])


CANON_FIELDS = ("sesso", "data_nascita", "comune_nascita", "provincia_nascita",
                "stato_nascita", "cittadinanza", "tipo_documento",
                "numero_documento", "luogo_rilascio")


def _transcribe_row(row: list, cmap: ColumnMap, *, stay_id, source_row):
    """One raw row -> (guests, stay_or_None), per the map.

    Dispatch, in order (the five dispositions):
      1. every cell empty           -> ([], None)          true blank
      2. no filled name slot, some cell filled -> RESIDUE (the floor):
         a. held vocabulary with a count ("+ 2 autisti")
                                    -> ([], held Stay)     pax_expected = text-N
            (no slot structure, so the text's count IS the count — unlike 3);
         b. anything else           -> ([], `unrecognized` Stay, pax 0)
            content the map cannot see NEVER silently vanishes: verbatim + row
            are kept and the stay BLOCKS completeness until a human looks
            (§8.5.7). A vocabulary miss costs a glance, never a false
            "complete".
      3. EVERY filled slot is a pax-count placeholder
                                    -> ([], held Stay)     held capacity (§13.4):
         deterministic recognition, takes precedence over any map-authored skip
         rule; pax_expected = the row's name-slot capacity (see stay.py) —
         the in-slot text-N is advisory only (park restates BLOCK totals); the
         placeholder text rides VERBATIM on the stay so nothing vanishes
         unreviewably (§8.5.7). A MIXED row (real name + placeholder slot) is
         NOT held — it falls through to guests and the name-plausibility guard
         reds the placeholder slot: ambiguity goes to a human, never arithmetic.
      4. otherwise                  -> (guests, named Stay) one Stay per row;
         a park-style twin = one Stay + two Guests linked by stay_id. A map's
         skip_row stays a REVIEW HINT, not a delete: a matched row that still
         carries a name is emitted with `skip_flag` set, so a real guest the
         model wrongly skipped surfaces (RED) instead of vanishing.
    """
    matched_skip = cmap.skip_row is not None and cmap.skip_row(row)
    flag = (cmap.skip_desc or "matched the map's skip rule") if matched_skip else ""

    filled = [(s, n) for s, n in (slot.extract(row) for slot in cmap.name_slots)
              if s or n]
    if not filled:
        residue = [c.strip() for c in row if c.strip()]
        if not residue:
            return [], None                           # true blank -> nothing
        text = " | ".join(residue)
        n = held_pax(text)
        if n is not None:
            # residue-held: no slot structure, so the text's N IS the count
            return [], Stay(stay_id=stay_id, pax_expected=n,
                            status="names_pending", verbatim=text,
                            source_row=source_row)
        # the floor: content the map cannot see becomes an unrecognized stay —
        # never dropped, blocks completeness until a human looks (§8.5.7)
        return [], Stay(stay_id=stay_id, pax_expected=0,
                        status="unrecognized", verbatim=text,
                        source_row=source_row)

    # held capacity — recognized in code, before (and regardless of) skip rules
    if all(held_pax(f"{s} {n}".strip()) is not None for s, n in filled):
        return [], Stay(
            stay_id=stay_id,
            pax_expected=len(cmap.name_slots),        # slot capacity, NOT text-N
            status="names_pending",
            verbatim=" | ".join(f"{s} {n}".strip() for s, n in filled),
            source_row=source_row,
        )

    vals = {f: _value(row, cmap.fields[f]) for f in CANON_FIELDS if f in cmap.fields}
    tipo = cmap.default_role
    if cmap.role_rule is not None:
        tipo = cmap.role_rule(row) or cmap.default_role

    guests = []
    for surname, nome in filled:
        guests.append(Guest(
            tipo_alloggiato=tipo, cognome=surname, nome=nome,
            sesso=vals.get("sesso", ""),
            data_nascita=vals.get("data_nascita", ""),
            stato_nascita=vals.get("stato_nascita", ""),
            cittadinanza=vals.get("cittadinanza", ""),
            born_in_italy=bool(vals.get("comune_nascita", "")),
            comune_nascita=vals.get("comune_nascita", ""),
            provincia_nascita=vals.get("provincia_nascita", ""),
            tipo_documento=vals.get("tipo_documento", ""),
            numero_documento=vals.get("numero_documento", ""),
            luogo_rilascio=vals.get("luogo_rilascio", ""),
            skip_flag=flag,
            stay_id=stay_id,
        ))
    named_stay = Stay(stay_id=stay_id, pax_expected=len(filled),
                      status="complete", source_row=source_row)
    return guests, named_stay


def transcribe_row(row: list, cmap: ColumnMap) -> list:
    """One raw row -> a list of canonical Guests (0, 1, or more), per the map.

    Guests-only view of _transcribe_row: a held or unrecognized row yields NO
    guests here (and its Stay is not visible) — use transcribe_with_stays or transcribe_report
    for the stays-aware account. Guests from this standalone view carry
    stay_id=None (there is no transcription-wide stay sequence to join)."""
    guests, _stay = _transcribe_row(row, cmap, stay_id=None, source_row=None)
    return guests


@dataclass
class TranscribeResult:
    """Stage 2's full output: the people AND the room-shaped units they occupy."""
    guests: list        # list[Guest]
    stays: list         # list[Stay] — named (complete) + held (names_pending)


def transcribe_with_stays(rows: list, cmap: ColumnMap) -> TranscribeResult:
    """Whole table -> TranscribeResult. One Stay per guest-yielding, held, or
    unrecognized row; guests link to their row's Stay via stay_id. Header rows
    and truly blank rows yield nothing."""
    guests, stays = [], []
    next_id = 1
    for idx, row in enumerate(rows):
        if idx < cmap.header_rows:
            continue
        gs, stay = _transcribe_row(row, cmap, stay_id=next_id, source_row=idx)
        if stay is not None:
            stays.append(stay)
            next_id += 1
        guests.extend(gs)
    return TranscribeResult(guests=guests, stays=stays)


def transcribe(rows: list, cmap: ColumnMap) -> list:
    """Whole table -> flat list of Guests (the stays-unaware view). Rows that
    matched the skip rule are emitted WITH skip_flag set; held and unrecognized
    rows become Stays (see transcribe_with_stays) and yield no guests."""
    return transcribe_with_stays(rows, cmap).guests


@dataclass
class TranscriptionReport:
    """Deterministic count reconciliation for one transcription pass — so a
    skip or a held row never causes a silent count delta."""
    input_rows: int
    header_rows: int
    data_rows: int
    guests: int
    skip_flagged: int
    skip_desc: str
    held_stays: int = 0        # rows recognized as held capacity (§13.4)
    held_pax: int = 0          # Σ pax_expected across held stays
    unrecognized_rows: int = 0 # rows the map cannot see (the floor) — kept as stays

    def summary(self) -> str:
        s = (f"input {self.input_rows} rows ({self.data_rows} data after "
             f"{self.header_rows} header), {self.guests} guests emitted")
        if self.skip_flagged:
            s += (f"; {self.skip_flagged} flagged for review by skip rule "
                  f"'{self.skip_desc or 'unnamed'}' (emitted, NOT dropped)")
        if self.held_stays:
            s += (f"; {self.held_stays} held row(s) -> held capacity, "
                  f"{self.held_pax} pax pending (kept as stays, NOT dropped)")
        if self.unrecognized_rows:
            s += (f"; {self.unrecognized_rows} row(s) the map cannot see -> "
                  f"unrecognized stays (kept verbatim, block completeness)")
        return s


def transcribe_report(rows: list, cmap: ColumnMap) -> TranscriptionReport:
    """transcribe(), plus an explicit account of skip-flagged, held, and
    unrecognized rows. Nothing with content is dropped: guest-yielding rows +
    held + unrecognized + true blanks == data rows."""
    res = transcribe_with_stays(rows, cmap)
    held = [s for s in res.stays if s.status == "names_pending"]
    unrec = [s for s in res.stays if s.status == "unrecognized"]
    guests = res.guests
    return TranscriptionReport(
        input_rows=len(rows),
        header_rows=cmap.header_rows,
        data_rows=max(0, len(rows) - cmap.header_rows),
        guests=len(guests),
        skip_flagged=sum(1 for g in guests if g.skip_flag),
        skip_desc=cmap.skip_desc,
        held_stays=len(held),
        held_pax=sum(s.pax_expected for s in held),
        unrecognized_rows=len(unrec),
    )
