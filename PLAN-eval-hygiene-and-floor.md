# PLAN — eval hygiene + the three engine holes

Branch: `eval-hygiene-and-floor` off `main` `17d9fae`.
Ground truth read verbatim before writing: `CLAUDE.md` (top to bottom),
`docs/eval-audit-2026-09-10.md`, `PLAN-eval-harness.md` §2/§7, and the
as-built `eval_harness.py` / `parser.py` / `validate.py`.
**STATUS: design brief — awaiting the user's pass. No code yet.**

**Baseline:** `./run_tests.sh` → **ALL GREEN (15/15)** at `17d9fae`,
working tree clean, `main` == `origin/main`.

Nothing under `holdout test data/` was read, and no test proposed here reads
it. Every new test uses synthetic rows or the four `data/` dev lists.

---

## 0. The one structural disagreement — A and B cannot land in that order

**A7 and B3 are mutually blocking. They must ship in the SAME commit, and the
engine commit must come first.** Measured, not assumed:

- **B3 alone breaks suite 15.** After the floor change, polish's two `Driver N`
  rows stop being guests. `eval/expectations/polish.json` still lists them
  among its 48 persons, so `recall` reports two missing persons, the polish
  verdict flips to FAIL, and `test_eval_harness.py::test_replay_corpus_pin`'s
  `assert card["summary"]["verdict"] == "PASS"` fails.
- **A7 alone breaks suite 15.** With the drivers removed from `persons` and
  `completeness` set to `awaiting_completion`, the parser still emits them as
  guests, so the hand parse computes `complete` and
  `test_self_check_dev_corpus`'s
  `assert out["soft"]["completeness"] == exp["completeness"]` fails.

Since main is never red and every commit must be green, the split becomes:

| commit | contents |
|---|---|
| **1 — engine floor** | B1, B2, B3 **+ A7** (the coupled `polish.json` edit) + every flipped test assertion |
| **2 — eval instrument** | A1, A2, A3, A4, A5, A6 |
| **3 — docs** | C |

This is the only place I depart from the brief's stated shape (A, then B).
The scopes are otherwise exactly as written. If you would rather keep A first,
the alternative is to land A7 inside commit 2 and accept that commit 1 leaves
`polish.json` briefly wrong — I do not recommend it; it makes commit 1 red.

---

## 1. Where I agree, with the evidence

Each call below was checked against the tree rather than taken on faith.

- **A2 — verified exactly as described.** In scorecard #1, excluding
  `review_notes` flips `identical_outcomes` to `True` for mix18, park **and**
  polish, and leaves textmail `False` — and textmail's difference is the real
  one (`field_coverage`: `tipo_documento` 46 in run 1, 0 in run 2, the
  `doc_type_passport` flip). So the de-noise turns a metric that is always
  `False` into one that fires on exactly the one genuine instability.
- **A5 — the redefinition is not a preference, it is a necessity.** Measured:
  the labels carry `data_nascita` for 47/47 and `numero_documento` for **46/47**
  (Hejnar Danuta has none in the source). The current gate demands
  `coverage == len(persons)`, so `required_fields: ["numero_documento"]` could
  never pass no matter how perfect extraction was. The redefinition
  (exact match among persons *carrying* an expected value) makes it 46/46.
- **A5 — the labels are safe to wire in.** I compared all 47 label records
  against the hand parse field-by-field: **zero mismatches** on
  `data_nascita`, `numero_documento` and `sesso`, including guest 27's
  double-space `TRW  495028`. The only divergence in the whole file is the
  `Ks.` name, which is exactly what A6 addresses.
- **A6 — already half-true, which simplifies it.**
  `eval/expectations/textmail.json` **already** carries
  `"Klimowicz Ks. Tomasz"`, the verbatim source form. So A6 requires no change
  to the expected name; it only adds `"role": "18"` as a soft field and
  updates the two `labels/` documents.
- **B1 — reproduced.** `norm_dotted_date("reserved 2 rooms till 10/07/2026")`
  raises `ValueError`, and inside `transcribe_with_stays` it aborts the
  **entire** transcription — one prose cell in a date column destroys a whole
  list. This is the most severe of the three holes.
- **B3 — no import cycle.** `validate.py` imports only `tracciato` plus
  stdlib; `stay.py` imports neither. `parser.py → validate.py → tracciato.py`
  is acyclic.
- **A1, A3, A4** — agreed as written, with implementation notes in §3.

## 2. Where I add a caveat (not a disagreement)

1. **`unrecognized_rows` as a soft metric leaves the floor ungated.** The
   audit's own lesson is that soft metrics do not gate. If a future map stopped
   triggering the floor, `recall` would still pass (the drivers are no longer
   expected persons) and only a soft number would move. I still recommend soft
   **for now** — the floor is directly guarded by `test_stay`, `test_textmail`
   and the new B3 pins, so the eval is not its only safety net — but it is a
   deliberate accepted gap and I would promote it to a gate once a second list
   carries residue rows.
2. **A thin `required_fields` gate can read as a strong one.** Under the new
   definition, a field with expected values on 2 of 47 persons passes at 2/2.
   Proposed mitigation, cheap: the gate detail records the denominator
   (`{"data_nascita": {"exact": 46, "of": 46}}`) so a thin gate is visible in
   the scorecard rather than hidden behind a green tick.
3. **`labels/textmail.json` does not exist under that name.** The file is
   `labels/text_mail_rooming_list_anonymized_ground_truth.json` (and `.xlsx`).
   Since A6 explicitly says to leave the xlsx as the human's original record, I
   propose **keeping both existing filenames** and referring to them by their
   real paths, rather than renaming the json and orphaning its spreadsheet
   twin. Say the word if you would prefer the rename.

## 3. The design calls, as they will be built

### A1 — holdout fence in code
`guard_path` refuses a path when **either** `real-data` appears as a path
segment **or** the normalized path contains `holdout test data`. Message names
which rule fired. Pinned in suite 15 alongside the existing `real-data/` pin.

### A2 — stability de-noise
The stability hash is computed over the soft dict **minus a
`_STABILITY_EXCLUDE` set**, initially `{"review_notes"}`. Named constant, not
an inline `pop`, so the exclusion list is visible and greppable.

### A3 — crash-guard breadth
`evaluate_run` wraps the `transcribe_with_stays` call. Any exception →
`gates["transcribe_error"] = "TypeError: …"`, `gates["map_valid"]` stays
`True` (the map *did* compile), and the list fails on a named gate instead of
killing the campaign. Complementary to B1, not redundant: B1 removes the
normalizer crash class; A3 catches everything else (the audit's wrong-typed
column indices still crash inside `NameSlot.extract`).

### A4 — retry wrapper
A small `_with_retry(call, *, attempts=3, sleep=time.sleep)` helper wrapping
**`anthropic_caller` only**. Retries on `urllib.error.URLError`,
`socket.timeout`, and `HTTPError` with `code == 429` or `500 <= code < 600`.
**Never** retries 401/403/400 — an auth or request error is not transient and
retrying wastes the user's spend. Backoff 1s, 2s, 4s. `sleep` is injected so
suite 15 tests the retry logic with a no-op and **the suite never sleeps**.
`replay_caller` is untouched, so offline behavior is byte-identical.

### A5 — hand labels wired in
Schema, additive and backward-compatible: each entry in `persons` is either a
string (today) or an object `{"name": …, "data_nascita": …,
"numero_documento": …, "sesso": …, "role": …}` with any subset of fields. A
loader normalizes both forms to `(name, fields_dict)` at the top of
`evaluate_transcribed`, so `match_persons` and `_field_coverage` keep taking
plain names and are untouched.

New soft metric `field_accuracy`: per field, `exact matches / persons with a
non-empty expected value`, matched by the existing token-multiset key.
`required_fields` is redefined to require **100% exact match** for the listed
fields among persons carrying an expected value, with the denominator
recorded per §2.2.

`eval/expectations/textmail.json` gets per-person `data_nascita` +
`numero_documento` (from the labels; `sesso` stays empty because the source
has no sex column) and `required_fields: ["data_nascita", "numero_documento"]`.
**mix18, polish and park get no per-person fields** — hand-labelled from the
documents in a later cycle. Bootstrapping them from the parser is precisely
the no-regression trap the audit named.

### A6 — the `Ks.` convention
Ground truth name stays the verbatim source cell (`Klimowicz` / `Ks. Tomasz`),
consistent with *verbatim means verbatim* and with what the expectations file
already says. The labeller's reading is recorded as `"role": "18"` on that
person — soft, never gating, because §13.3 makes role a later audited step.
`labels/…ground_truth.json` and `labels/README.md` are updated to state the
convention; the `.xlsx` is left as the human's original record with the
divergence noted, as instructed.

### A7 — polish expectations (ships in commit 1)
`persons` 48 → 46 (drop `Driver 1`, `Driver 2`); add
`"unrecognized_rows": 2`; `completeness` `"complete"` →
`"awaiting_completion"`. Harness reports `unrecognized_rows` observed vs
expected as a soft metric.

### B1 — normalizer crash guard
`parser._value` wraps the normalizer call; on **any** exception it returns the
raw stripped cell. The validator then reds it — never invented, never dropped,
never a crashed run. This preserves *null is a valid answer* and *verbatim*
simultaneously: the cell reaches canonical exactly as the document wrote it.

### B2 — two additive normalizers
- `sex_mf`: `m|f|male|female|maschio|femmina` (case-insensitive, stripped) →
  `"1"` / `"2"`; **anything else verbatim** (never guessed).
- `ymd_date`: `1989.02.04` / `1989-02-04` / `1989/02/04` → `04/02/1989`;
  a 2-digit year is returned **verbatim** per the never-invent rule; anything
  it does not confidently recognize is returned verbatim rather than raised
  (matching `norm_dotted_date`'s existing fallback, and belt-and-braces with
  B1).

Both are added to `build_prompt`'s normalizer bullets. **No existing fixture
or hand map uses them, so `llm_maps/*.json` and every parity pin are
untouched** — this is an additive contract change, not a fixture-breaking one.

**Ambiguity note, deliberate:** `ymd_date` is year-first by declaration. The
dd/mm vs mm/dd question for `dotted_date` remains **stage 1's declaration to
make, not code's guess** — the engine will not sniff locale, and a wrong
declaration surfaces as an implausible date in review, not as a silent
reinterpretation.

### B3 — disposition 3b, the count-less placeholder floor
In `_transcribe_row`, after the held check and before guests: if **every**
filled name slot fails the implausible-name test, the row becomes an
`unrecognized` Stay (`pax_expected=0`, `verbatim` = the joined slot text,
`source_row` set). Mixed rows (real name + placeholder slot) are unchanged —
guests plus a guard red — because *ambiguity goes to a human, never to
arithmetic*.

`validate._implausible_name` is promoted to public `implausible_name`. Two
call sites move (`validate.py:124`, `test_name_plausibility.py:26/61/68`); no
compatibility alias, because the repo is self-contained and a dead alias is
exactly the kind of drift this project keeps paying for.

**Truly-empty rows are unaffected** and must stay that way: rows with no
filled slot return early, before this check. Verified — polish rows 50–51
have zero non-empty cells and will continue to produce nothing. The
dispatch-floor invariant "the floor must not invent stays for empty rows"
survives intact, and commit 1 keeps a pin for it.

**`"tba"` — I take it.** Today `_implausible_name("TBA")` returns `None`: no
digits, no listed token, so a `TBA` row would become a **guest named TBA**
whose name field raises no red at all. `tbd` is already in the set; `tba` is
its literal sibling, so this completes an existing pair rather than opening a
new category. The counter-argument deserves recording: `stay.py`'s comment
warns that growing vocabulary without dev-data evidence is the enumeration
trap, and no dev list contains `TBA`. I judge the pair-completion argument
stronger for a *backstop* whose failure mode is a false negative, and I am
adding **only** `tba` — not `n.n.`, `xxx` or `unknown`, which would be
speculative growth.

---

## 4. Blast radius, file by file

**Commit 1 — engine floor**

- `parser.py` — `_value` crash guard (B1); `sex_mf` + `ymd_date` in
  `NORMALIZERS` (B2); disposition 3b in `_transcribe_row` (B3); import of
  `implausible_name` from `validate`.
- `validate.py` — `_implausible_name` → `implausible_name`; `"tba"` added to
  `NAME_PLACEHOLDER_TOKENS`. **No tier logic, no gate logic, no message
  wording changed.**
- `llm_parser.py` — two bullets added to `build_prompt`'s normalizer list.
  `SKIP_RULES`, `ROLE_RULES`, `parse_map_json` and both callers untouched.
- `eval/expectations/polish.json` — A7.
- Tests: `test_parser`, `test_stay`, `test_name_plausibility`,
  `test_skip_nondestructive`, `test_llm_parser`, `test_export`,
  `test_eval_harness` (see §5).

**Commit 2 — eval instrument**

- `eval_harness.py` — `guard_path` (A1); `_STABILITY_EXCLUDE` (A2);
  transcribe guard (A3); persons-schema loader, `field_accuracy`, redefined
  `required_fields`, `unrecognized_rows` soft metric (A5, A7-reporting).
- `llm_parser.py` — `_with_retry` + `anthropic_caller` wrapping (A4).
- `eval/expectations/textmail.json` — per-person fields, `required_fields`,
  `role` on guest 1 (A5, A6).
- `labels/…ground_truth.json`, `labels/README.md` — A6 convention.
- `test_eval_harness.py` — new pins (see §5).

**Commit 3 — docs:** `README.md`, `README_START_HERE.md`, `CLAUDE.md`.

**Untouched, and I will verify with `git diff --stat` before each commit:**
`tracciato.py`, `stay.py`, `storage.py`, `export.py`, `orchestrator.py`,
`infer.py`, `maps.py`, `build_golden.py`, `golden/`, `llm_maps/*.json`,
`run.py`, `run_lists.py`, `run_llm.py`, `parse_mix18.py`, `data/`.

## 5. Every changed assertion, old → new

**Commit 1**

| file | old | new |
|---|---|---|
| `test_stay.py:168` | polish `len(guests) == 55` | `== 53` |
| `test_stay.py:168` | polish `len(stays) == 55` | **stays 55** (53 complete + 2 unrecognized) — unchanged number, different composition; assertion re-worded to say so |
| `test_stay.py:169` | polish `not [s if unrecognized]` | exactly 2 unrecognized, both `Driver N`, plus a **retained** pin that rows 50–51 (truly empty) still invent nothing |
| `test_stay.py:171` | polish completeness `"complete"` | `"awaiting_completion"` |
| `test_skip_nondestructive.py:83` | `len(p_real) == 48` | `== 46` |
| `test_skip_nondestructive.py:84` | `len(p_flagged) == 7` | **unchanged** — the 7 legend rows carry no digits/tokens and stay emit-and-flag |
| `test_skip_nondestructive.py:86–87` | 2 Driver **guests**, no skip_flag | 0 Driver guests; 2 `unrecognized` stays carrying `Driver 1`/`Driver 2` verbatim |
| `test_llm_parser.py:23` | POLISH expected `55` | `53` |
| `test_name_plausibility.py` (backstop block) | `"names pending"` / `"TBD"` emitted as 2 guard-red guests | 0 guests, 2 `unrecognized` stays; the guard remains pinned for **mixed** rows, which still produce a guard-red guest |
| `test_name_plausibility.py::test_polish_driver_placeholders_flagged` | 2 Driver guests, red, non-submittable | renamed to `…_become_unrecognized`: 2 unrecognized stays, zero Driver guests |
| `test_name_plausibility.py:124` | comment "the only placeholders left among guests are the Drivers" | corrected: none reach the guest list; the placeholder branch is kept meaningful by a synthetic **mixed** row |
| `test_export.py:69` | "red guests are bookings" anchored on a **Driver** row | re-anchored on a skip-flagged legend row (still RED via `skip_flag`, still a guest, still in the artifact) — the invariant is unchanged, only the fixture |
| `test_export.py:181` | polish delta `== 55` | `== 53` |
| `test_eval_harness.py:167` | polish `matched == 48` | `== 46`, plus `unrecognized == 2` |

New pins in commit 1: the B1 prose-in-date-column row (transcription
completes, cell verbatim, validator reds it); `sex_mf` and `ymd_date`
unit cases including 2-digit-year-verbatim; `implausible_name("TBA")`;
mixed-row unchanged; truly-empty-row unchanged.

**Commit 2** — additive only; no existing assertion changes. New pins: the
`holdout test data` refusal; stability identical-with-notes-differing;
`transcribe_error` verdict from a wrong-typed map; retry succeeds on the 3rd
attempt and does **not** retry a 401, with an injected no-op sleep;
`field_accuracy` maths; `required_fields` passing at 46/46 for
`numero_documento` and failing when a value is wrong; textmail self-check
still aces its own (now richer) expectations.

**Commit 3** — docs only, no assertions.

## 6. Invariants NOT weakened

- **Golden byte identity** — `tracciato.py`, `build_golden.py` and `golden/`
  are untouched; `test_tracciato` is not in the blast radius.
- **Verbatim means verbatim** — B1 returns the **raw** cell on normalizer
  failure; B3 stores the joined slot text **verbatim** on the unrecognized
  stay; A6 keeps the source form as the expected name.
- **Null is a valid answer** — no new value is ever invented: `sex_mf` and
  `ymd_date` pass unrecognized input through unchanged, and 2-digit years stay
  as written.
- **Emit-and-flag** — untouched for its actual domain. The 7 polish legend
  rows still emit with `skip_flag` → RED. B3 only takes rows where *every*
  filled slot is an implausible label, which produce no real person.
- **Zero real guests dropped** — B3 moves the 2 Driver rows from
  guard-red guests to unrecognized stays. Both dispositions are non-silent and
  both block submission; the unrecognized one additionally **blocks
  completeness**, which is strictly stronger. No row loses its text, and the
  count reconciliation still accounts for every input row.
- **Nothing vanishes unreviewably** — strengthened, not weakened: a `TBA` row
  that today becomes a plausible-looking guest becomes a completeness-blocking
  unrecognized stay.
- **The one architectural rule** — no new LLM call sites; `build_prompt` gains
  two descriptive bullets only.
- **The holdout** — A1 makes the seal executable for the first time.

## 7. Test plan

`./run_tests.sh` before and after **every** commit; **suite count stays 15** —
all new tests go into existing suites (B1/B2 → `test_parser`; B3 →
`test_stay` + `test_name_plausibility`; A1–A5 → `test_eval_harness`). **No
count sweep is needed**, and CLAUDE.md will say so explicitly.

Beyond the pins in §5: a synthetic adversarial pass for B3 (rows whose slots
hold `TBA`, `TBD`, `names pending`, `---`, `2 pax` mixed with a real name) and
for B1 (normalizers fed prose, empty strings, and wrong types), all on
synthetic rows. `run.py`, `run_lists.py`, `run_llm.py` are run after commits 1
and 2; the only expected output change anywhere is polish `55 → 53` in
`run_lists.py`.

**No live API calls in this cycle.** A4 is tested with an injected fake
caller; the eval is exercised via `--replay` only. A live campaign to see
`field_accuracy` on real model output is the natural follow-up, and it is
yours to trigger.

## 8. Out of scope (named, so nothing sprawls)

Hand-labelling mix18/polish/park from the documents (the real fix for the
audit's ground-truth finding — a later cycle, deliberately not bootstrapped);
promoting `unrecognized_rows` to a gate; the `held_row` prompt unfreeze and
the textmail stage-1 fixture; type-validation inside `parse_map_json`;
room-type-column mapping; the Bedzzle builder; the app tiers; any live run.

---

## 9. Postscript — approved (2026-09-10)

Approved as drawn. The three caveats from §2 are resolved as follows, and two
additions were made to the build.

- **Caveat 1 — resolved: `unrecognized_rows` stays a SOFT metric.** Promotion
  to a hard gate waits for a **second list carrying residue rows**; with only
  polish's two Driver rows in the corpus, a gate would be pinned to a single
  list's shape. The floor itself remains directly guarded by `test_stay`,
  `test_textmail` and the new B3 pins, so this is a reporting gap, not a
  safety one. Revisit when the corpus grows.
- **Caveat 2 — taken.** The `required_fields` gate detail records
  matched / expected / total-persons, e.g.
  `{"data_nascita": "47/47 of 47", "numero_documento": "46/46 of 47"}`, so a
  gate that is green only because ground truth is thin is visible as such.
- **Caveat 3 — resolved: keep both existing `labels/` filenames.** No rename;
  the json and its spreadsheet twin stay together under their descriptive
  names.

**Addition to A3.** `transcribe_error` must be added to the gate-name tuple in
`evaluate_list`, so it participates in `passed` rather than sitting in the
detail dict unread. Pinned with an injected map whose transcription raises:
that list FAILS and **the campaign continues** to the remaining lists.

**Addition to A4.** Retry **only** on timeouts, 429 and 5xx; any other 4xx
raises immediately (an auth or malformed-request error is not transient, and
retrying it burns the user's spend for nothing). Both behaviors pinned with a
fake `urlopen` and an injected no-op sleep.
