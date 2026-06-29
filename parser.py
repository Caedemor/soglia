"""
Soglia — generalized stage-2 parser (map-driven transcription).

STAGE 1 understanding (which column is which) -> a ColumnMap.   [LLM, later]
STAGE 2 transcription (follow the map, build Guests) -> here.   [THIS FILE]

Grown to handle the variety in three real lists:
  - one OR two (or more) people per row, via name_slots;
  - a combined "SURNAME Firstname" cell OR separate surname/first-name columns;
  - blank rows skipped automatically; a map may also supply a skip_row hint
    (e.g. held "names pending" placeholder rows);
  - field cleaning is format-only (e.g. 05.12.1984 -> 05/12/1984), never meaning.
Anything not mapped is left empty so the validator surfaces it. What stage 2
CANNOT do (e.g. recognise that "GUIDE NOWAK" hides a role marker) is left for
stage 1 / review.
"""
from dataclasses import dataclass, field
from typing import Callable, Optional

from tracciato import Guest

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
                if len(y) == 2:           # 2-digit year -> 20YY (rooming lists are near-future)
                    y = "20" + y
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


def _value(row: list, rule: FieldRule) -> str:
    if rule.const is not None:
        return rule.const
    if rule.column is None or rule.column >= len(row):
        return ""
    return NORMALIZERS[rule.normalizer](row[rule.column])


CANON_FIELDS = ("sesso", "data_nascita", "comune_nascita", "provincia_nascita",
                "stato_nascita", "cittadinanza", "tipo_documento",
                "numero_documento", "luogo_rilascio")


def transcribe_row(row: list, cmap: ColumnMap) -> list:
    """One raw row -> a list of canonical Guests (0, 1, or more), per the map."""
    if cmap.skip_row is not None and cmap.skip_row(row):
        return []

    vals = {f: _value(row, cmap.fields[f]) for f in CANON_FIELDS if f in cmap.fields}
    tipo = cmap.default_role
    if cmap.role_rule is not None:
        tipo = cmap.role_rule(row) or cmap.default_role

    guests = []
    for slot in cmap.name_slots:
        surname, nome = slot.extract(row)
        if not surname and not nome:
            continue                                  # empty slot -> no guest (handles blanks)
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
        ))
    return guests


def transcribe(rows: list, cmap: ColumnMap) -> list:
    """Whole table -> flat list of Guests, skipping header rows and empty/held rows."""
    out = []
    for r in rows[cmap.header_rows:]:
        out.extend(transcribe_row(r, cmap))
    return out
