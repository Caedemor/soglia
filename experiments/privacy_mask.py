"""
Soglia — deterministic PII masker for the privacy architecture.

Idea: real passport data must never reach the cloud model. Stage 1 only needs
to infer WHICH COLUMN IS WHAT (a ColumnMap), which is a question about
structure, not content. So we send the model a STRUCTURE-PRESERVING but
PII-scrubbed copy of the sample rows; stage 2 then applies the returned map to
the REAL rows locally.

This masker is plain Python — NO model calls, reliable by construction:
  - alphabetic char -> random alphabetic char, same case and same script
    (Latin->Latin, Cyrillic->Cyrillic);
  - digits -> random digits, but a date-shaped cell stays a valid calendar date
    in the IDENTICAL written format (same separators, same widths, same order);
  - a document-number cell keeps its exact letter/digit pattern;
  - left UNTOUCHED: header rows, structural markers (GUIDE / DRIVER /
    TOUR-LEADER / Ks. / Sig. / room+board codes), column order, empty cells,
    whitespace, casing.

Determinism: a seeded RNG, so the same input always yields the same masked
output (reproducible), while the substituted characters are not the originals.
"""
import random
import re
import string

# ---- script/case-aware character pools -------------------------------------
CYR_UPPER = [chr(c) for c in range(0x0410, 0x0430)]          # А..Я
CYR_LOWER = [chr(c) for c in range(0x0430, 0x0450)]          # а..я


def _rand_letter(ch, rng):
    """A random letter of the same case and (approx) same script as `ch`."""
    if "a" <= ch <= "z":
        return rng.choice(string.ascii_lowercase)
    if "A" <= ch <= "Z":
        return rng.choice(string.ascii_uppercase)
    o = ord(ch)
    if 0x0410 <= o <= 0x042F or ch in "ЁЄІЇҐ":               # Cyrillic upper
        return rng.choice(CYR_UPPER)
    if 0x0430 <= o <= 0x044F or ch in "ёєіїґ":               # Cyrillic lower
        return rng.choice(CYR_LOWER)
    # Latin diacritics (Polish ą ł ż …) and anything else: same-case Latin.
    if ch.isupper():
        return rng.choice(string.ascii_uppercase)
    if ch.islower():
        return rng.choice(string.ascii_lowercase)
    return ch


def _mask_alpha(s, rng):
    return "".join(_rand_letter(c, rng) if c.isalpha() else c for c in s)


# ---- structural tokens that must survive verbatim --------------------------
MARKERS = {
    # roles / honorifics
    "GUIDE", "DRIVER", "TOUR-LEADER", "TOURLEADER", "LEADER", "PILOT",
    "KS", "SIG", "SIGRA", "SIGNORA", "SIGNOR", "MR", "MRS", "MS", "DR",
    "PROF", "REV", "FR",
    # room / board codes
    "SGL", "DBL", "DUS", "TWN", "TWIN", "TRP", "TPL", "QUAD", "QDR",
    "BB", "HBB", "FB", "HB", "RO", "AI", "VIP", "PAX", "SUITE", "JUNIOR",
}


def _is_marker(tok):
    return tok.strip().strip(".").upper() in MARKERS


# ---- date-shaped cells -----------------------------------------------------
_DATE_RE = re.compile(r"^\s*\d{1,4}([./-])\d{1,2}\1\d{1,4}\s*$")


def _looks_like_date(s):
    return bool(_DATE_RE.match(s))


def _mask_date(s, rng):
    """Keep separators, component widths and order; produce a valid calendar date.
    Both non-year components are drawn <=12 so the date is valid regardless of
    whether the format is dd/mm or mm/dd — we never reorder or reinterpret it."""
    sep = _DATE_RE.match(s).group(1)
    core = s.strip()
    out = []
    for p in core.split(sep):
        if len(p) == 4:
            out.append(str(rng.randint(1940, 2015)))
        elif len(p) == 2:
            out.append(str(rng.randint(1, 12)).zfill(2))
        elif len(p) == 1:
            out.append(str(rng.randint(1, 9)))
        else:
            out.append(p)
    return s.replace(core, sep.join(out))


# ---- document-number cells (letter/digit mix) ------------------------------
def _looks_like_docnum(s):
    t = s.strip()
    if len(t) < 5 or _looks_like_date(s):
        return False
    has_alpha = any(c.isalpha() for c in t)
    has_digit = any(c.isdigit() for c in t)
    clean = all(c.isalnum() or c == " " for c in t)
    return has_alpha and has_digit and clean


def _mask_docnum(s, rng):
    def f(c):
        if c.isdigit():
            return str(rng.randint(0, 9))
        if c.isalpha():
            return _rand_letter(c, rng)
        return c
    return "".join(f(c) for c in s)


# ---- name cells: mask name tokens, preserve marker/numeric tokens ----------
# Optional fake-name pools (plain Python, NO model) for the targeted fallback.
_FAKE = {
    "latin_sur": ["Rossi", "Bianchi", "Kowalski", "Nowak", "Smith", "Brown",
                  "Muller", "Garcia", "Novak", "Horvat", "Adams", "Clark"],
    "latin_giv": ["Marco", "Anna", "Piotr", "Maria", "John", "Eva", "Luca",
                  "Sara", "Pawel", "Julia", "Tomas", "Lena"],
    "cyr_sur":   ["Іванів", "Петрів", "Коваль", "Бондар", "Шевчук", "Мороз"],
    "cyr_giv":   ["Олена", "Іван", "Марія", "Андрій", "Наталя", "Сергій"],
}


def _fake_token(tok, rng):
    """Replace a name token with a plausible-but-fake name of the same script,
    preserving leading capitalization and overall casing (UPPER vs Title)."""
    cyr = any(0x0400 <= ord(c) <= 0x04FF for c in tok)
    pool = (_FAKE["cyr_sur"] + _FAKE["cyr_giv"]) if cyr else (_FAKE["latin_sur"] + _FAKE["latin_giv"])
    pick = rng.choice(pool)
    if tok.isupper():
        return pick.upper()
    return pick


def _mask_name_cell(s, rng, fake):
    out = []
    for tok in s.split(" "):
        if tok == "" or _is_marker(tok) or any(c.isdigit() for c in tok):
            out.append(tok)                       # preserve markers & numeric placeholders
        elif any(c.isalpha() for c in tok):
            out.append(_fake_token(tok, rng) if fake else _mask_alpha(tok, rng))
        else:
            out.append(tok)
    return " ".join(out)


def _mask_cell(s, rng, fake):
    if not s.strip():
        return s
    toks = s.split()
    if any(_is_marker(t) for t in toks):          # "SGL 1", "GUIDE NOWAK", "Ks. X"
        return _mask_name_cell(s, rng, fake)
    if _looks_like_date(s):
        return _mask_date(s, rng)
    if _looks_like_docnum(s):
        return _mask_docnum(s, rng)
    if any(c.isalpha() for c in s):               # names, group labels
        return _mask_name_cell(s, rng, fake)
    if any(c.isdigit() for c in s):               # booking numbers, counts
        return "".join(str(rng.randint(0, 9)) if c.isdigit() else c for c in s)
    return s


def mask_sample(rows, header_rows=1, seed=20260630, fake_names=False):
    """Return a masked copy of `rows`. The first `header_rows` rows (column
    labels) are preserved verbatim; data rows have their PII cells scrubbed."""
    rng = random.Random(seed)
    out = []
    for i, row in enumerate(rows):
        if i < header_rows:
            out.append(list(row))
        else:
            out.append([_mask_cell(c, rng, fake_names) for c in row])
    return out


# ============================================================================
# PART 2 — pair-aware anonymization: ONE per-unique-token mapping shared by a
# SET of files (e.g. an original + its supplement), so the same real person
# receives the identical fake identity everywhere and families keep a shared
# (fake) surname. Plain Python, NO model calls, seeded => reproducible.
#
# Roles a column can carry: 'surname' | 'given' | 'dob' | 'docnum' |
# 'issue' | 'expiry' | 'remark'.  Anything without a role is left verbatim
# (room column, guest numbers, titles, held/reservation notes, markers).
# ============================================================================

_WS_RE = re.compile(r"^(\s*)(.*?)(\s*)$", re.DOTALL)  # \s matches NBSP too

# Suffix classes for surname generation: keep the morphological "feel".
_SURNAME_SUFFIXES = ["ENKO", "CHUK", "SHKO", "OVA", "INA", "SKA", "ETS",
                     "IUK", "UK", "OV"]
_ROOT_CONS = ["B", "D", "H", "K", "L", "M", "N", "P", "R", "S", "T", "V",
              "Z", "ZH", "SH", "CH", "KH", "TS"]
_ROOT_VOW = ["A", "E", "I", "O", "U", "Y"]
_ROOT_CONS_CYR = ["Б", "Д", "Г", "К", "Л", "М", "Н", "П", "Р", "С", "Т",
                  "В", "З", "Ж", "Ш", "Ч", "Х", "Ц"]
_ROOT_VOW_CYR = ["А", "Е", "И", "О", "У", "І"]

# Ukrainian-transliteration given-name pools (checked against the real token
# set at build time; a syllable fallback covers exhaustion/collisions).
_GIVEN_POOL_F = ["KATERYNA", "KHRYSTYNA", "ZORIANA", "MYROSLAVA", "ROKSOLANA",
                 "ORYSIA", "USTYNA", "YARYNA", "ZLATA", "LESIA", "OLESIA",
                 "MARTA", "POLINA", "ALINA", "KARYNA", "TAISIIA", "SNIZHANA",
                 "KALYNA", "ODARKA", "MOTRIA", "YEVHENIIA", "LIUBOV", "VIRA",
                 "DARYNA", "IVANNA", "YUSTYNA", "HORPYNA", "ORYNA", "VARVARA",
                 "YAROSLAVA", "STEFANIIA", "BOZHENA", "MALVINA", "SOLOMIIA"]
_GIVEN_POOL_M = ["PETRO", "DMYTRO", "VASYL", "OSTAP", "TARAS", "YURII",
                 "IHOR", "MYKOLA", "ROMAN", "ARTEM", "MARKIIAN", "OREST"]
# Male given names present in the corpora we handle (default = female pool;
# heuristic below catches the common -O/-R/-M/-II male endings as backup).
_GIVEN_MALE = {"OLEKSANDR", "SERHII", "ANDRII", "MAKSYM", "TYMOFII",
               "KOSTIANTYN", "PETRO", "DMYTRO", "IVAN", "OLEH", "VOLODYMYR",
               "VITALII", "YAROSLAV", "BOHDAN", "DENYS", "ARTEM", "NAZAR"}


def _is_cyr(tok):
    return any(0x0400 <= ord(c) <= 0x04FF for c in tok)


def _parse_dmy(tok):
    """Parse a strictly day-first 'dd.mm.yyyy'-shaped token (any of ./-
    separators, 4-digit year LAST). Returns (d, m, y, sep, widths)."""
    m = _DATE_RE.match(tok)
    if not m:
        raise ValueError("not a date token: %r" % tok)
    sep = m.group(1)
    parts = tok.strip().split(sep)
    if len(parts[2]) != 4:
        raise ValueError("year-last 4-digit dates only, got %r" % tok)
    return (int(parts[0]), int(parts[1]), int(parts[2]), sep,
            [len(p) for p in parts])


def _render_dmy(d, m, y, sep, widths):
    return sep.join([str(d).zfill(widths[0]), str(m).zfill(widths[1]),
                     str(y).zfill(widths[2])])


def _is_adult(d, m, y, ref):
    """True if born (d,m,y) is >= 18 years old on ref=(ry,rm,rd)."""
    ry, rm, rd = ref
    return (y, m, d) <= (ry - 18, rm, rd)


class PairMasker:
    """One shared real->fake mapping over the UNION of several parsed tables.

    Usage:  pm = PairMasker(seed=...);
            pm.register(rows, roles) for EVERY file first;   # union pass
            pm.finalize();                                   # build mapping
            masked = pm.mask_rows(rows, roles) per file.     # apply pass
    """

    def __init__(self, seed=20260805, ref_date=(2026, 7, 24)):
        self.rng = random.Random(seed)
        self.ref = ref_date
        self.finalized = False
        self.real_tokens = set()       # every real alpha token (upper), both files
        self.real_dates = set()        # every real date token (stripped)
        self.real_docs = set()         # normalized (space-stripped) doc numbers
        self.surname_toks = []         # encounter-ordered unique
        self.given_toks = []
        self.dob_toks = []
        self.issue_toks = []
        self.expiry_pairs = []         # (expiry_tok, issue_tok or None)
        self.map_surname = {}
        self.map_given = {}
        self.map_date = {}             # one namespace: same token => same fake
        self.map_doc = {}

    # ---- pass 1: registration over the union ------------------------------
    def register(self, rows, roles):
        assert not self.finalized
        for row in rows:
            issue_tok = None
            for ci, cell in enumerate(row):
                role = roles.get(ci)
                if role == "issue" and cell.strip():
                    issue_tok = cell.strip()
            for ci, cell in enumerate(row):
                core = _WS_RE.match(cell).group(2)
                if not core:
                    continue
                role = roles.get(ci)
                for t in core.split():
                    if any(c.isalpha() for c in t):
                        self.real_tokens.add(t.upper())
                if role in ("dob", "issue", "expiry") and _looks_like_date(core):
                    self.real_dates.add(core)
                if role == "docnum":
                    self.real_docs.add(core.replace(" ", ""))
                if role == "surname":
                    for t in core.split():
                        if (t and not _is_marker(t)
                                and not any(c.isdigit() for c in t)
                                and t not in self.surname_toks):
                            self.surname_toks.append(t)
                elif role == "given":
                    for t in core.split():
                        if (t and not _is_marker(t)
                                and not any(c.isdigit() for c in t)
                                and t not in self.given_toks):
                            self.given_toks.append(t)
                elif role == "dob" and _looks_like_date(core):
                    if core not in self.dob_toks:
                        self.dob_toks.append(core)
                elif role == "issue" and _looks_like_date(core):
                    if core not in self.issue_toks:
                        self.issue_toks.append(core)
                elif role == "expiry" and _looks_like_date(core):
                    if core not in [e for e, _ in self.expiry_pairs]:
                        self.expiry_pairs.append((core, issue_tok))

    # ---- fake generators ---------------------------------------------------
    def _gen_root(self, length, cyr=False):
        cons = _ROOT_CONS_CYR if cyr else _ROOT_CONS
        vow = _ROOT_VOW_CYR if cyr else _ROOT_VOW
        out = ""
        while len(out) < max(length, 2):
            out += self.rng.choice(cons) + self.rng.choice(vow)
        return out[:max(length, 2)]

    def _unique(self, candidate_fn, taken):
        for _ in range(500):
            c = candidate_fn()
            if c and c not in taken and c.upper() not in self.real_tokens:
                return c
        raise RuntimeError("could not generate a unique fake token")

    def _build_surnames(self):
        taken = set()
        toks = list(self.surname_toks)
        # Gendered pairs first: X and X+'A' both present share one fake root.
        pair_males = sorted(t for t in toks if t + "A" in toks)
        for male in pair_males:
            suffix = next((s for s in _SURNAME_SUFFIXES
                           if male.endswith(s) and len(male) > len(s) + 1), None)
            if suffix is None:
                suffix = male[-2:]
            cyr = _is_cyr(male)
            root_len = len(male) - len(suffix)

            def cand():
                f = self._gen_root(root_len, cyr) + suffix
                return f if (f + "A") not in taken and (f + "A").upper() not in self.real_tokens else None
            fake = self._unique(cand, taken)
            self.map_surname[male] = fake
            self.map_surname[male + "A"] = fake + "A"
            taken.update({fake, fake + "A"})
        for tok in toks:
            if tok in self.map_surname:
                continue
            suffix = next((s for s in _SURNAME_SUFFIXES
                           if tok.endswith(s) and len(tok) > len(s) + 1), None)
            if suffix is None:
                suffix = tok[-2:]
            cyr = _is_cyr(tok)
            root_len = len(tok) - len(suffix)
            fake = self._unique(
                lambda: self._gen_root(root_len, cyr) + suffix, taken)
            self.map_surname[tok] = fake
            taken.add(fake)

    def _build_givens(self):
        taken = set()
        pool_f = [n for n in _GIVEN_POOL_F if n not in self.real_tokens]
        pool_m = [n for n in _GIVEN_POOL_M if n not in self.real_tokens]
        self.rng.shuffle(pool_f)
        self.rng.shuffle(pool_m)
        for tok in self.given_toks:
            # A doubled first letter is a source typo pattern — carry it.
            doubled = len(tok) > 3 and tok[0] == tok[1]
            base = tok[1:] if doubled else tok
            male = (base.upper() in _GIVEN_MALE)
            pool = pool_m if male else pool_f
            if pool:
                fake = pool.pop()
            else:
                fake = self._unique(
                    lambda: self._gen_root(len(base), _is_cyr(tok)), taken)
            if doubled:
                fake = fake[0] + fake
            if not tok.isupper():
                fake = fake.capitalize()
            self.map_given[tok] = fake
            taken.add(fake)

    def _fake_date(self, tok, keep_band=None, keep_future_side=False):
        d, m, y, sep, widths = _parse_dmy(tok)
        real_adult = _is_adult(d, m, y, self.ref)
        real_future = (y, m, d) > (self.ref[0], self.ref[1], self.ref[2])
        for _ in range(2000):
            y2 = y + self.rng.randint(-2, 2)
            m2 = self.rng.randint(1, 12)
            d2 = self.rng.randint(1, 28)
            if keep_band and _is_adult(d2, m2, y2, self.ref) != real_adult:
                continue
            if keep_future_side and ((y2, m2, d2) > self.ref) != real_future:
                continue
            out = _render_dmy(d2, m2, y2, sep, widths)
            if out == tok or out in self.real_dates or out in self.map_date.values():
                continue
            return out
        raise RuntimeError("no fake date found for %r" % tok)

    def _build_dates(self):
        for tok in self.dob_toks:
            if tok not in self.map_date:
                self.map_date[tok] = self._fake_date(tok, keep_band=True)
        for tok in self.issue_toks:
            if tok not in self.map_date:
                self.map_date[tok] = self._fake_date(tok, keep_future_side=True)
        # expiry = fake issue + the REAL (expiry - issue) component delta,
        # so +10y / +4y validity spans and source anomalies stay visible.
        for tok, issue_tok in self.expiry_pairs:
            if tok in self.map_date:
                continue
            if issue_tok is None or issue_tok not in self.map_date:
                self.map_date[tok] = self._fake_date(tok, keep_future_side=True)
                continue
            rd, rm, ry, sep, widths = _parse_dmy(tok)
            id_, im, iy, _, _ = _parse_dmy(issue_tok)
            fd, fm, fy, fsep, fw = _parse_dmy(self.map_date[issue_tok])
            y2 = fy + (ry - iy)
            m2 = fm + (rm - im)
            while m2 > 12:
                m2 -= 12
                y2 += 1
            while m2 < 1:
                m2 += 12
                y2 -= 1
            d2 = min(max(fd + (rd - id_), 1), 28)
            self.map_date[tok] = _render_dmy(d2, m2, y2, sep, widths)

    def _build_docs(self):
        taken = set()
        for norm in sorted(self.real_docs):
            if not norm:
                continue

            def cand():
                return "".join(
                    str(self.rng.randint(0, 9)) if c.isdigit()
                    else _rand_letter(c, self.rng) if c.isalpha() else c
                    for c in norm)
            fake = self._unique(
                lambda: (lambda f: f if f not in self.real_docs else None)(cand()),
                taken)
            self.map_doc[norm] = fake
            taken.add(fake)

    def finalize(self):
        assert not self.finalized
        self._build_surnames()
        self._build_givens()
        self._build_dates()
        self._build_docs()
        self.finalized = True

    # ---- pass 2: application ----------------------------------------------
    def _mask_core(self, core, role):
        if role in ("surname", "given"):
            mapping = self.map_surname if role == "surname" else self.map_given
            out = []
            for t in core.split(" "):
                if t == "" or _is_marker(t) or any(c.isdigit() for c in t):
                    out.append(t)
                elif t in mapping:
                    out.append(mapping[t])
                elif any(c.isalpha() for c in t):
                    raise KeyError("unmapped %s token %r" % (role, t))
                else:
                    out.append(t)
            return " ".join(out)
        if role in ("dob", "issue", "expiry"):
            if not _looks_like_date(core):
                raise ValueError("non-date in %s column: %r" % (role, core))
            return self.map_date[core]
        if role == "docnum":
            fake = self.map_doc[core.replace(" ", "")]
            chars = iter(fake)
            return "".join(next(chars) if c.isalnum() else c for c in core)
        if role == "remark":
            # Free text (health/diet/accessibility, names…): nothing may
            # survive. Markers and digits keep structure; words are destroyed.
            return _mask_name_cell(core, self.rng, fake=False)
        return core

    def mask_cell(self, text, role):
        assert self.finalized
        if role is None:
            return text
        lead, core, trail = _WS_RE.match(text).groups()
        if not core:
            return text                       # empty / NBSP cells stay put
        return lead + self._mask_core(core, role) + trail

    def mask_rows(self, rows, roles):
        return [[self.mask_cell(c, roles.get(ci)) for ci, c in enumerate(row)]
                for row in rows]

    def mapping_dump(self):
        return {"surnames": self.map_surname, "givens": self.map_given,
                "dates": self.map_date, "docnums": self.map_doc}


# ---- structure-preserving write-back ---------------------------------------
def docx_logical_rows(path):
    import docx
    return [[c.text for c in r.cells] for r in docx.Document(path).tables[0].rows]


def mask_docx(in_path, out_path, roles, masker, skip_rows=(0,)):
    """Copy `in_path` to `out_path` masking only gridSpan-1 cells whose grid
    column has a role. Merged cells (titles, held/reservation notes), the room
    and counter columns, markers and empties survive byte-verbatim; run-level
    replacement keeps character formatting."""
    import docx
    from docx.oxml.ns import qn
    from docx.table import _Cell
    doc = docx.Document(in_path)
    table = doc.tables[0]
    for ri, tr in enumerate(table.rows):
        if ri in skip_rows:
            continue
        col = 0
        for tc in tr._tr.findall(qn("w:tc")):
            tcPr = tc.find(qn("w:tcPr"))
            span = 1
            if tcPr is not None:
                gs = tcPr.find(qn("w:gridSpan"))
                if gs is not None:
                    span = int(gs.get(qn("w:val")))
            role = roles.get(col) if span == 1 else None
            if role is not None:
                cell = _Cell(tc, table)
                old = cell.text
                new = masker.mask_cell(old, role)
                if new != old:
                    p = cell.paragraphs[0]
                    if p.runs:
                        p.runs[0].text = new
                        for r in p.runs[1:]:
                            r.text = ""
                    else:
                        p.add_run(new)
                    for extra in cell.paragraphs[1:]:
                        for r in extra.runs:
                            r.text = ""
            col += span
    doc.save(out_path)


def mask_xlsx(in_path, out_path, roles, masker, skip_rows=(0,)):
    """Cell-by-cell write-back into a copy of the workbook via openpyxl:
    merges, layout and formatting survive because only cell VALUES change."""
    import openpyxl
    wb = openpyxl.load_workbook(in_path)
    ws = wb.active
    merged_starts = {r.min_row - 1 for r in ws.merged_cells.ranges}
    for ri, row in enumerate(ws.iter_rows()):
        if ri in skip_rows:
            continue
        for ci, cell in enumerate(row):
            role = roles.get(ci)
            if role is None or not isinstance(cell.value, str):
                continue
            new = masker.mask_cell(cell.value, role)
            if new != cell.value:
                cell.value = new
    wb.save(out_path)
    return merged_starts


def mask_txt(in_path, out_path, roles, masker, skip_rows=(0,), sep="\t"):
    """Strict-TSV text mail: mask role columns, keep everything else and the
    line structure byte-verbatim. UTF-8 in, UTF-8 out."""
    with open(in_path, encoding="utf-8") as f:
        lines = f.read().split("\n")
    out = []
    for li, line in enumerate(lines):
        if li in skip_rows or sep not in line:
            out.append(line)
            continue
        cells = line.split(sep)
        out.append(sep.join(masker.mask_cell(c, roles.get(ci))
                            for ci, c in enumerate(cells)))
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
