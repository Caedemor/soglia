"""
Soglia — inference (ADVISORY suggestions; an optional layer ON TOP of canonical data).

This is a NICE-TO-HAVE add-on, deliberately decoupled from the base:
  - it never mutates a Guest in place and never overwrites a value that is present;
  - it only PROPOSES values for EMPTY required fields;
  - it returns Suggestions the human accepts or rejects in review.
Delete this file and parse / validate / format are completely unaffected.

Two sources, both local — nothing leaves the machine:
  1. name -> sex, via a small curated lookup table. An unknown name yields NO
     suggestion (the field correctly stays red); culturally ambiguous names are
     refused on purpose (the Andrea / Nicola problem).
  2. list-level defaults -> citizenship / birthplace, from a hint the caller
     supplies ("this is a Ukrainian operator's list" -> propose Ukraine),
     offered as confirmable suggestions, never assumed silently.
"""
from dataclasses import dataclass, replace

from tracciato import Guest

# first name (UPPER-cased, Latin or Cyrillic) -> sex code: "1" = M, "2" = F.
# Curated to cover the names in the real test lists; grows as needed.
_NAME_SEX = {
    # female
    "IRYNA": "2", "ІРИНА": "2", "VIKTORIIA": "2", "DARIA": "2", "SOFIIA": "2",
    "MARIIA": "2", "DIANA": "2", "VERONIKA": "2", "YANA": "2", "LARYSA": "2",
    "MARHARYTA": "2", "DARYNA": "2", "KHRYSTYNA": "2", "RUSLANA": "2",
    "VALENTYNA": "2", "TAMARA": "2", "SNIZHANA": "2", "ALLA": "2", "NINA": "2",
    "YARYNA": "2", "MYROSLAVA": "2", "SOLOMIIA": "2", "POLINA": "2",
    "BOHDANA": "2", "YEVHENIIA": "2", "LILIIA": "2", "ROKSOLANA": "2",
    # male
    "ARTEM": "1", "BOHDAN": "1", "БОГДАН": "1", "АНДРІЙ": "1",
}

# Names that flip sex across cultures — never auto-suggest, always leave to human.
_AMBIGUOUS = {"ANDREA", "NICOLA", "SIMONE", "JEAN", "MARIA", "MICHELE"}


@dataclass
class Suggestion:
    field: str          # a Guest field name
    value: str          # the proposed value
    basis: str          # human-readable reason, shown in review
    confidence: str     # "high" | "medium" | "low"

    def __repr__(self):
        return f"suggest {self.field}={self.value!r} [{self.confidence}] — {self.basis}"


def _sex_from_name(nome: str):
    key = nome.strip().upper()
    if key in _AMBIGUOUS:
        return None
    return _NAME_SEX.get(key)


def suggest(guest: Guest, *, list_country_code: str = None,
            list_country_name: str = None) -> list:
    """Return suggestions for this guest's EMPTY fields. Never overwrites."""
    out = []

    if not guest.sesso.strip():
        code = _sex_from_name(guest.nome)
        if code:
            who = "female" if code == "2" else "male"
            out.append(Suggestion("sesso", code,
                                   f"first name {guest.nome!r} → {who} (lookup table)", "high"))

    if list_country_code:
        if not guest.cittadinanza.strip():
            out.append(Suggestion("cittadinanza", list_country_code,
                                   f"list-level default: {list_country_name} operator / passports",
                                   "medium"))
        if not guest.born_in_italy and not guest.stato_nascita.strip():
            out.append(Suggestion("stato_nascita", list_country_code,
                                   f"list-level default: born in {list_country_name} (confirm at desk)",
                                   "low"))

    return out


def apply_suggestions(guest: Guest, suggestions: list) -> Guest:
    """Return a NEW Guest with the given suggestions filled in (caller decides which)."""
    return replace(guest, **{s.field: s.value for s in suggestions})
