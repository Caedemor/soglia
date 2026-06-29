"""
Soglia — canonical validation (the advisory pre-check that drives red / yellow).

Given a post-extraction canonical Guest, return the issues a human must see in
review. This is the COMPLETENESS GATE: per guest, "which required Alloggiati
fields are missing or impossible," kept separate from "are we sure we read this
right" (that confidence signal comes from extraction provenance, built later).

Principle (handoff §13.8): this is ADVISORY. The portal's elaborazione is the
authority. We surface problems early; we do not replicate the portal's rules.
Per §13.7, a RED does not hard-block — the human may override and export — but
nothing reaches the formatter clean until reds are resolved or overridden.

Tiers:
  RED    — blocks a clean submission: a required field missing, an impossible
           value, or too long to fit the fixed-width record.
  YELLOW — worth a glance, not blocking (mostly produced upstream by extraction;
           a few are derivable here).
"""
from dataclasses import dataclass
from datetime import date

from tracciato import Guest, HEAD_TYPES, MEMBER_TYPES, FIELD_SPEC

VALID_TIPI = HEAD_TYPES | MEMBER_TYPES          # {"16","17","18","19","20"}
VALID_SESSO = {"1", "2"}
WIDTHS = dict(FIELD_SPEC)
MAX_PLAUSIBLE_AGE = 120


@dataclass
class Issue:
    field: str          # matches a FIELD_SPEC name, so the UI can point at the cell
    tier: str           # "red" | "yellow"
    message: str        # what the hotelier sees

    def __repr__(self):
        return f"{self.tier.upper()}({self.field}): {self.message}"


def _parse_ddmmyyyy(s: str):
    """Return a date, or None if it isn't a real gg/mm/aaaa date (e.g. 30/02/1992)."""
    parts = s.strip().split("/")
    if len(parts) != 3:
        return None
    try:
        d, m, y = (int(p) for p in parts)
        return date(y, m, d)
    except (ValueError, TypeError):
        return None


def validate_guest(g: Guest, *, today: date = None) -> list:
    """Return the list of Issues for one guest. Empty list = clean."""
    today = today or date.today()
    issues = []
    is_head = g.tipo_alloggiato in HEAD_TYPES

    def red(field, msg):
        issues.append(Issue(field, "red", msg))

    # tipo alloggiato
    if g.tipo_alloggiato not in VALID_TIPI:
        red("tipo_alloggiato", f"tipo alloggiato non valido: {g.tipo_alloggiato!r}")

    # sesso
    if g.sesso not in VALID_SESSO:
        red("sesso", f"sesso deve essere 1 (M) o 2 (F), trovato {g.sesso!r}")

    # cognome / nome — present and within width
    if not g.cognome.strip():
        red("cognome", "cognome mancante")
    elif len(g.cognome) > WIDTHS["cognome"]:
        red("cognome", f"cognome troppo lungo ({len(g.cognome)} > {WIDTHS['cognome']})")
    if not g.nome.strip():
        red("nome", "nome mancante")
    elif len(g.nome) > WIDTHS["nome"]:
        red("nome", f"nome troppo lungo ({len(g.nome)} > {WIDTHS['nome']})")

    # data di nascita — present, real, plausible
    if not g.data_nascita.strip():
        red("data_nascita", "data di nascita mancante")
    else:
        d = _parse_ddmmyyyy(g.data_nascita)
        if d is None:
            red("data_nascita", f"data di nascita non valida: {g.data_nascita!r}")
        elif d > today:
            red("data_nascita", f"data di nascita nel futuro: {g.data_nascita}")
        elif today.year - d.year > MAX_PLAUSIBLE_AGE:
            red("data_nascita", f"data di nascita non plausibile: {g.data_nascita}")

    # luogo di nascita — Italy needs comune + provincia; abroad needs stato
    if g.born_in_italy:
        if not g.comune_nascita.strip():
            red("comune_nascita", "comune di nascita mancante (nato in Italia)")
        if not g.provincia_nascita.strip():
            red("provincia_nascita", "provincia di nascita mancante (nato in Italia)")
    else:
        if not g.stato_nascita.strip():
            red("stato_nascita", "stato di nascita mancante")

    # cittadinanza
    if not g.cittadinanza.strip():
        red("cittadinanza", "cittadinanza mancante")

    # documents — required for heads (ospite singolo / capo); members carry none
    if is_head:
        if not g.tipo_documento.strip():
            red("tipo_documento", "tipo documento mancante (ospite singolo / capo)")
        if not g.numero_documento.strip():
            red("numero_documento", "numero documento mancante (ospite singolo / capo)")
        elif len(g.numero_documento) > WIDTHS["numero_documento"]:
            red("numero_documento",
                f"numero documento troppo lungo ({len(g.numero_documento)} > {WIDTHS['numero_documento']})")
        if not g.luogo_rilascio.strip():
            red("luogo_rilascio", "luogo di rilascio mancante (ospite singolo / capo)")

    return issues


def is_submittable(g: Guest, *, today: date = None) -> bool:
    """True if the guest has no RED issues (clean enough to format without override)."""
    return not any(i.tier == "red" for i in validate_guest(g, today=today))
