"""
Soglia — Alloggiati Web "tracciato" formatter (the byte-exact police-file kernel).

CONTRACT: the input is POST-REVIEW canonical data — roles already assigned,
values already resolved, reference codes already looked up. This module's ONLY
job is to place those values into the fixed-width 168-character record layout.

Explicitly NOT this module's job (separate pieces, built later):
  - reading messy lists (extraction)      - looking up reference codes
  - validation / completeness (red/yellow) - the today/yesterday arrival rule
The formatter trusts that its input is complete and valid. If something is too
long to fit, it raises instead of silently truncating a police record.

Layout + the head/member document rule follow the handoff's §4.2 / §8.2 reading
of the official manual. The reference codes that appear in fixtures are
PLACEHOLDERS standing in for the real Questura tables — the formatter only
*places* codes, it does not know them.
"""

from dataclasses import dataclass

# --- The record layout: the single source of truth. (field_name, width), in order.
#     Widths must sum to 168. Taken from handoff §4.2.
FIELD_SPEC = [
    ("tipo_alloggiato",    2),
    ("data_arrivo",       10),
    ("giorni_permanenza",  2),
    ("cognome",           50),
    ("nome",              30),
    ("sesso",              1),
    ("data_nascita",      10),
    ("comune_nascita",     9),
    ("provincia_nascita",  2),
    ("stato_nascita",      9),
    ("cittadinanza",       9),
    ("tipo_documento",     5),
    ("numero_documento",  20),
    ("luogo_rilascio",     9),
]
RECORD_LENGTH = 168
assert sum(w for _, w in FIELD_SPEC) == RECORD_LENGTH, "field widths must total 168"

# Tipo-alloggiato codes that count as a "head" and therefore carry the three
# document fields. Members are covered under their head and leave them blank.
HEAD_TYPES = {"16", "17", "18"}    # ospite singolo, capo famiglia, capo gruppo
MEMBER_TYPES = {"19", "20"}        # familiare, membro gruppo


@dataclass
class Guest:
    """One canonical, post-review person. All codes are pre-resolved strings."""
    tipo_alloggiato: str           # "16".."20"
    cognome: str
    nome: str
    sesso: str                     # "1" = M, "2" = F
    data_nascita: str              # "gg/mm/aaaa"
    stato_nascita: str             # 9-char state code
    cittadinanza: str              # 9-char state code
    born_in_italy: bool = False
    comune_nascita: str = ""       # comune code — only when born_in_italy
    provincia_nascita: str = ""    # 2-char — only when born_in_italy
    # Document fields — used only for HEAD types; blank for members.
    tipo_documento: str = ""       # e.g. "PASOR"
    numero_documento: str = ""
    luogo_rilascio: str = ""       # 9-char place code


def _field_values(g: Guest) -> dict:
    """Resolve each layout field from the guest, applying the two branching rules."""
    is_head = g.tipo_alloggiato in HEAD_TYPES
    return {
        "tipo_alloggiato":   g.tipo_alloggiato,
        # data_arrivo / giorni_permanenza are supplied at format time (submission)
        "cognome":           g.cognome,
        "nome":              g.nome,
        "sesso":             g.sesso,
        "data_nascita":      g.data_nascita,
        # born abroad -> comune + provincia stay blank; only stato is set
        "comune_nascita":    g.comune_nascita if g.born_in_italy else "",
        "provincia_nascita": g.provincia_nascita if g.born_in_italy else "",
        "stato_nascita":     g.stato_nascita,
        "cittadinanza":      g.cittadinanza,
        # document fields only for heads; members carry blanks (covered by head)
        "tipo_documento":    g.tipo_documento if is_head else "",
        "numero_documento":  g.numero_documento if is_head else "",
        "luogo_rilascio":    g.luogo_rilascio if is_head else "",
    }


def format_schedina(g: Guest, *, data_arrivo: str, giorni_permanenza: int) -> str:
    """Render ONE guest to a 168-char line: space-padded, left-aligned, fixed width."""
    values = _field_values(g)
    values["data_arrivo"] = data_arrivo
    values["giorni_permanenza"] = str(giorni_permanenza).zfill(2)

    parts = []
    for name, width in FIELD_SPEC:
        raw = values.get(name, "")
        if len(raw) > width:
            # NEVER silently truncate (handoff §8.2). Validation should have caught
            # this upstream; if it reaches the formatter, fail loudly.
            raise ValueError(
                f"field {name!r} value {raw!r} is {len(raw)} chars, exceeds width "
                f"{width} — canonical validation should have flagged this as red"
            )
        parts.append(raw.ljust(width))

    line = "".join(parts)
    assert len(line) == RECORD_LENGTH, f"built {len(line)} chars, expected {RECORD_LENGTH}"
    return line


def format_tracciato(guests, *, data_arrivo: str, giorni_permanenza: int) -> str:
    """Render the whole file: one line per guest, CR+LF between lines, NO trailing newline."""
    lines = [
        format_schedina(g, data_arrivo=data_arrivo, giorni_permanenza=giorni_permanenza)
        for g in guests
    ]
    return "\r\n".join(lines)
