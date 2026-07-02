# PLAN — dispatch floor (commit 1.5: no row with content ever vanishes)

Branch: `dispatch-floor` off main `7108904`. Motivation: the text-mail trailer
(`+ 2 autisti`) proved the dispatch's "blank" disposition is a lie — a row with
no NAME-SLOT content but real cells was dropped silently, producing a **false
"complete" (47/47/0)** with two people missing. This commit builds the
categorical floor so that failure class is impossible in any vocabulary, then
demotes the held recognizer to an arithmetic convenience on top of it.

## 1. The design

**Dispatch v2 — five dispositions** (order matters):
1. every cell empty                      → nothing (true blank);
2. no filled name slot, some cell filled → **residue**:
   a. held vocabulary with a count found → held Stay, `pax_expected = text-N`;
   b. otherwise                          → **`unrecognized` Stay**,
      `pax_expected = 0`, verbatim = the joined cells, source_row set;
3. every filled slot is a held placeholder → held Stay, `pax_expected =
   len(name_slots)` (unchanged, commit-1 rule);
4. otherwise → guests + named Stay (incl. emit-and-flag on skip match;
   unchanged).

**The floor rule:** `completeness_status` returns `complete` only when
`pending == 0` AND `unrecognized == 0`. An unrecognized row costs a human a
glance; it can never cost a silent false-complete. This is the
name-plausibility guard's philosophy (judge by CATEGORY, never by matching a
string) applied to the one place it was missing.

**pax_expected authority split** (extends commit 1's rule, same evidence
standard):
- IN-SLOT placeholders: slot capacity, text-N is advisory — park's text
  restates block totals; naive text-sum = **161**, slot-derived truth = **18**
  (pinned in tests now).
- RESIDUE (slotless) placeholders: **text-N is authoritative** — the trailer
  has no slot structure; slot capacity would say 1, the text's 2 IS the count.

**Vocabulary:** `\b(\d{1,3})\s*(?:pax|autist[ai])\b`. `driver` stays OUT:
"Driver 2" is an index, not a count (two such rows = two people at pax 1, not
pax 2); polish's drivers remain guard-red guests. Reclassifying them is a
named follow-up (see §5), not this commit.

**Documented sharp edge (accepted):** a residue totals row containing held
vocabulary ("47 pax totale") would read as held-47 — pending 47, loudly wrong,
never silently complete. No dev-data row has this shape; no denylist yet
(denylists are the enumeration trap this commit exists to escape). The floor
guarantees loud failure; tests pin that plain "Totale: 47" lands unrecognized.

**Deviation flagged — reconciliation json shape:** `reconcile()` gains an
`"unrecognized"` count next to §8.5.6's `{expected, named, pending, overage}`.
Unrecognized rows contribute ZERO to the arithmetic (attention count, not
pax); the key exists so completeness and the UI can see them. Justification:
§8.5.7 ("drop and forget fails both lenses") is the same document's own
principle; §8.5.6's json assumed the map sees every row. The addendum's
completeness enum is kept (no new status value); unrecognized blocks
`complete` via the existing `awaiting_completion`.

**Frozen this commit:** ColumnMap JSON contract, `llm_parser.py`, all
fixtures, `validate.py`, `storage.py` (a new status string round-trips free),
`tracciato.py`/golden (tripwire), `maps.py`, `orchestrator.py` (its
`completeness()` passes reconcile's dict through unchanged).

## 2. Census (empirical grounding, run on main@7108904)

Rows yielding nothing today, per list: mix18 **0**; park **0**; polish **2,
both truly empty** (rows 50–51 — no hidden content, so polish gains no
unrecognized stays and its counts/completeness are untouched); textmail **1**
— the trailer, the only residue row in all four lists. Blast radius on
existing lists: textmail gains one held stay; everything else byte-stable.

## 3. File-by-file

- `stay.py` — vocabulary regex; docstrings record the authority split, the
  driver exclusion, the totals sharp edge; `Stay.status` values now
  `names_pending | complete | unrecognized`; `reconcile()` counts
  unrecognized; `completeness_status()` gains the floor rule.
- `parser.py` — `_transcribe_row` residue branch (2a/2b above); dispatch
  docstring rewritten for five dispositions; `TranscriptionReport` gains
  `unrecognized_rows` + summary clause; module docstring bullet updated.
- `CLAUDE.md` — file-map parser line "four-way" → "five-way"; the
  nothing-vanishes invariant gains the unrecognized floor; the "Text-mail
  trailer gap" open item is REPLACED by two named follow-ups: (a) stage-1
  `held_row` hint — the deliberate contract unfreeze (prompt + all fixtures +
  a hand-authored `llm_maps/textmail.json` together), floor stays the
  guarantee beneath it; (b) the polish Driver-rows decision (in-slot
  reclassification to held pax-1; moves counts across four suites; own blast
  radius).
- `README_START_HERE.md` — textmail line reflects the held trailer;
  passenger fix: step 4's "three sample lists" → four (stale since the
  textmail commit).
- Tests (every change listed in §4): `test_textmail.py`, `test_stay.py`.
- ZERO changes: `run_tests.sh` (still 11), `README.md`, everything frozen
  above.

## 4. Test plan + every changed assertion (old → new)

- `test_textmail.py` — `test_trailer_known_gap` FLIPS to
  `test_trailer_is_held` (the pin working as designed): held_pax("+ 2
  autisti") None → **2**; held stays [] → **one** (pax_expected **2**, verbatim
  "+ 2 autisti", source_row 47, zero linked guests); stays 47 → **48**; guests
  47 unchanged, no leak; NEW: reconcile == {expected **49**, named 47, pending
  **2**, overage 0, unrecognized 0} and completeness **complete →
  awaiting_completion** — the false-complete transition asserted explicitly;
  NEW: report shows held_stays 1 / held_pax 2 / unrecognized_rows 0. Module
  docstring loses the known-gap framing.
- `test_stay.py` — recognizer units add "2 autisti"/"1 autista" → 2/1,
  "Driver 2"/"2 drivers" still None; park gains the authority pin
  (naive text-sum over held verbatims == **161** ≠ derived 18); NEW
  `test_residue_floor`: "Totale: 47" residue row → unrecognized stay (NOT
  held-47), blocks complete, verbatim+source_row kept; all-empty row still
  yields nothing; reconcile dict equalities gain `"unrecognized": 0` (three
  sites); `test_other_lists_complete` additionally asserts polish/mix18 have
  zero unrecognized (census-backed).
- All other suites: unchanged and must stay green — polish/mix18/park counts
  are byte-stable per §2.

Invariants NOT weakened: golden byte-identity, verbatim, null-is-valid,
emit-and-flag, zero real guests dropped or reclassified, commit-1 arithmetic
(park 41/23/18) intact.

## 5. Explicitly out of scope

Stage-1 `held_row` hint (layer 3); polish Driver reclassification; any
denylist for totals vocabulary; room-type-column mapping. All recorded in
CLAUDE.md open items so the next session trips over them.
