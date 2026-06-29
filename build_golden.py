"""
Independently-built golden file for the "family twin" fixture.

Built field-by-field with explicit .ljust() literals — deliberately NOT using
tracciato.FIELD_SPEC or the formatter's loop — so a bug in the formatter can't
hide by being mirrored here. THIS FILE IS THE AUTHORITY; the formatter must
reproduce it byte-for-byte.

Human-verifiable against handoff §4.2: each line is 168 chars; run the test to
print the field-by-field offset breakdown and eyeball it.

NOTE — two things baked in here are spec readings to verify against the real
manual before trusting in production:
  (1) reference codes are PLACEHOLDERS (Ukraine state code, passport type code);
  (2) the rule that a *familiare* (member) leaves the 3 document fields BLANK.
If either changes, edit the relevant literal(s) below + the formatter branch and
re-run the test — it will confirm nothing else moved.
"""
import os

UKR = "100000999"   # PLACEHOLDER Alloggiati state code for Ukraine (replace w/ real table)
PASS = "PASOR"      # passport (ordinary) document-type code per §4.2 reading (verify)
ARR = "12/06/2026"  # arrival — in production this is stamped at submission (today/yesterday)
GIO = "02"          # nights: 12 -> 14 June


def line(parts):
    s = "".join(parts)
    assert len(s) == 168, f"line is {len(s)} chars, expected 168"
    return s


# Guest 1 — KOVALCHUK IRYNA, capo famiglia (17), F, born in Ukraine, passport FZ180350.
g1 = line([
    "17",                  # tipo alloggiato (head)
    ARR,                   # data arrivo
    GIO,                   # giorni permanenza
    "KOVALCHUK".ljust(50), # cognome
    "IRYNA".ljust(30),     # nome
    "2",                   # sesso (F)
    "23/02/1958",          # data nascita
    "".ljust(9),           # comune nascita — blank (born abroad)
    "".ljust(2),           # provincia nascita — blank (born abroad)
    UKR.ljust(9),          # stato nascita
    UKR.ljust(9),          # cittadinanza
    PASS.ljust(5),         # tipo documento (head)
    "FZ180350".ljust(20),  # numero documento (head)
    UKR.ljust(9),          # luogo rilascio (head)
])

# Guest 2 — KOVALCHUK ARTEM, familiare (19), M, born in Ukraine.
# He HAS a passport in the source list, but as a member the 3 document fields
# are left blank (he is covered under the capo famiglia).
g2 = line([
    "19",                  # tipo alloggiato (member)
    ARR,
    GIO,
    "KOVALCHUK".ljust(50),
    "ARTEM".ljust(30),
    "1",                   # sesso (M)
    "17/09/2014",
    "".ljust(9),           # comune nascita — blank (born abroad)
    "".ljust(2),           # provincia nascita — blank (born abroad)
    UKR.ljust(9),          # stato nascita
    UKR.ljust(9),          # cittadinanza
    "".ljust(5),           # tipo documento — BLANK (member)
    "".ljust(20),          # numero documento — BLANK (member)
    "".ljust(9),           # luogo rilascio — BLANK (member)
])

# Guest 3 — ROSSI MARCO, ospite singolo (16), M, born IN Italy (Milano).
# Exercises the other birth branch: comune + provincia are FILLED, and an
# Italian-born guest still has Italy as stato nascita + cittadinanza.
ITA = "100000100"   # PLACEHOLDER Alloggiati state code for Italy (replace w/ real table)
MILANO = "015146"   # PLACEHOLDER comune code for Milano (real codes are Belfiore-style)
g3 = line([
    "16",                  # tipo alloggiato (ospite singolo — a head, carries documents)
    ARR,
    GIO,
    "ROSSI".ljust(50),
    "MARCO".ljust(30),
    "1",                   # sesso (M)
    "08/11/1990",
    MILANO.ljust(9),       # comune nascita — FILLED (born in Italy)
    "MI".ljust(2),         # provincia nascita — FILLED (born in Italy)
    ITA.ljust(9),          # stato nascita
    ITA.ljust(9),          # cittadinanza
    "IDENT".ljust(5),      # tipo documento — carta d'identità
    "CA12345AB".ljust(20), # numero documento
    MILANO.ljust(9),       # luogo rilascio (a comune, here Milano)
])

GOLDEN = "\r\n".join([g1, g2, g3])   # CR+LF between lines, no trailing newline


if __name__ == "__main__":
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "family_twin.txt")
    # newline="" so Python writes our \r\n exactly, with no translation
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(GOLDEN)
    print(f"wrote {path}  ({len(GOLDEN)} bytes, {GOLDEN.count(chr(13)+chr(10))+1} schedine)")
