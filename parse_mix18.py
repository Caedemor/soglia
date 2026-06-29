"""
Soglia — parser for the MIX18 Ukrainian tour list (Park Hotel Salice Terme).

SCOPE: a LIST-SPECIFIC parser for one real layout — NOT the general extractor
(that's the LLM step, later). It proves the path: real .docx table -> canonical
Guest objects -> validate. It reads only what the table contains and makes its
assumptions explicit; anything the list does NOT carry is left empty so the
validator surfaces it honestly rather than the parser quietly inventing it.

Assumptions (all provisional, all flagged):
  - Name cell is "SURNAME Firstname": surname = first token, nome = the rest,
    kept VERBATIM (mixed Cyrillic / Latin scripts preserved; transliteration is
    a separate concern).
  - The document is a passport (the column is "Паспорт"); the type code "PASOR"
    is a PLACEHOLDER pending the real Questura table.
  - Role / party assignment uses the SIMPLEST default: treat the whole list as
    one tour gruppo — TOUR-LEADER = capo gruppo (18), everyone else = membro
    gruppo (20). The real structure (per-booking parties) is richer — see the
    report — and proper role assignment is its own slice.
  - Fields absent from this list are left EMPTY: sesso, birthplace (comune /
    stato), cittadinanza, luogo rilascio. The validator flags them; an inference
    slice (sex from name; citizenship / birthplace from the tour context) is next.
"""
from dataclasses import dataclass
from datetime import datetime

import docx
from tracciato import Guest

# Single source of truth for the path lives in maps.py (relative ./data).
from maps import MIX18_DOCX as DOCX
PASSPORT_CODE = "PASOR"   # PLACEHOLDER document-type code (verify vs manual)

# Column indices in the table (header row 0).
C_NAME, C_IN, C_OUT, C_DOB, C_PASS, C_ROOM, C_ORDER, C_BOARD = 1, 2, 3, 4, 5, 6, 7, 8


@dataclass
class Parsed:
    guest: Guest
    row: int
    raw_name: str
    room: str          # stay label, e.g. "TWIN 2"
    order: str         # booking key / marker, e.g. "66836361618" | "TOUR-LEADER" | "DRIVER"
    board: str
    nights: int
    role_note: str     # how the role was assigned (provisional)


def _to_slash_date(dotted: str) -> str:
    """'05.12.1984' -> '05/12/1984'; '' -> ''."""
    return dotted.replace(".", "/") if dotted.strip() else ""


def _nights(check_in: str, check_out: str) -> int:
    fmt = "%d.%m.%y"
    return (datetime.strptime(check_out, fmt) - datetime.strptime(check_in, fmt)).days


def split_name(full: str):
    """'KOVALCHUK IRYNA' -> ('KOVALCHUK', 'IRYNA'). Surname-first, verbatim."""
    toks = full.split()
    if len(toks) <= 1:
        return full, ""
    return toks[0], " ".join(toks[1:])


def parse(path: str = DOCX):
    table = docx.Document(path).tables[0]
    out = []
    for ri, row in enumerate(table.rows[1:], start=1):
        c = [cell.text.strip() for cell in row.cells]
        surname, nome = split_name(c[C_NAME])
        order = c[C_ORDER]
        passport = c[C_PASS]

        is_leader = order.upper() == "TOUR-LEADER"
        is_driver = order.upper() == "DRIVER"
        if is_leader:
            tipo = "18"   # capo gruppo
            role_note = "capo gruppo (TOUR-LEADER marker) [provisional one-group default]"
        else:
            tipo = "20"   # membro gruppo
            role_note = ("membro gruppo (DRIVER — service staff?) [needs review]"
                         if is_driver else
                         "membro gruppo [provisional one-group default]")

        guest = Guest(
            tipo_alloggiato=tipo,
            cognome=surname,
            nome=nome,
            sesso="",                          # not in this list
            data_nascita=_to_slash_date(c[C_DOB]),
            stato_nascita="",                  # not in this list
            cittadinanza="",                   # not in this list
            born_in_italy=False,
            comune_nascita="", provincia_nascita="",
            tipo_documento=(PASSPORT_CODE if passport else ""),
            numero_documento=passport,
            luogo_rilascio="",                 # not in this list
        )
        out.append(Parsed(
            guest=guest, row=ri, raw_name=c[C_NAME], room=c[C_ROOM], order=order,
            board=c[C_BOARD], nights=_nights(c[C_IN], c[C_OUT]), role_note=role_note,
        ))
    return out
