# PLAN — the stage-1 eval harness (the instrument before the campaign)

Branch: `eval-harness` off main `322f04f` (tag: engine-complete). First
cycle whose ground truth is not an addendum section: the spec is the
EMPIRICAL RECORD — rev5 §7 (re-measure methodology: guest-level parity
under the current dispatch) and §8 (the closing battery: what varies
benignly, what must never vary) — plus the standing rules (caller
injection, gitignored `*.live.json`, holdout sealed, repo-is-the-record).
STATUS: design brief — awaiting approval, no implementation yet.

## 1. What the record settled (design inputs, not forks)

- **The unit of truth is guest-level outcome, not map-level similarity.**
  June's park maps were 0/4 on map-parity and the OUTCOME was perfect;
  the harness scores what reaches the engine, not how the model phrased
  the map.
- **Divergence has two classes**, demonstrated live: catastrophic-if-silent
  (a missing person, an uncompilable map, a broken engine path) and
  benign-but-worth-tracking (junk-row disposition, role choice, unmapped
  optional fields, run-to-run judgment variance). The harness must GATE on
  the first class and REPORT the second — hard-failing on benign variance
  would teach us to ignore the harness.
- **The record split already has policy:** raw model output → dated,
  gitignored `llm_maps/<list>.<date>.live.json`; the durable result → a
  committed artifact. The harness writes both; committing stays a human
  act.
- **Live execution belongs to Claude Code** (the user's standing
  directive): this sandbox designs, builds, and hermetically pins the
  instrument; every live run happens on the machine with the key.

## 2. The design calls (each vetoable)

1. **Ground truth = a small, human-authored EXPECTATIONS file per list**
   (`eval/expectations/<list>.json`), NOT a hand-written ColumnMap per
   list. Expectations carry what a human can assert by looking at the
   document: the persons (verbatim names), total held pax, junk-row count
   (disposition free), and per-field coverage counts. This is the labor
   model for the future ~20: minutes per list, not the hour a full map
   costs — and it measures the model against the DOCUMENT, not against
   our own prior mapping opinions. The four dev lists' existing hand maps
   remain as a BONUS scorer (map-outcome parity) where present.
2. **Hard gates vs soft metrics.** Gates (any failure = list FAILS, exit
   code nonzero): the map compiles (`parse_map_json` accepts it); **100%
   expected-person recall**; held-pax arithmetic exact (Σ pax_expected of
   held stays == expected); the FULL engine path runs green on the live
   output (persist → completeness → PMS artifact → export → confirm →
   coverage `full`). Soft metrics (reported, never failing): junk
   disposition, `default_role` choice, field-coverage deltas, extras
   (guests beyond expectations — reported loudly, but junk-as-guest is the
   emit-and-flag design working, not a model failure), and K-run
   stability. §13.3 makes role a later audited step; the battery proved
   junk disposition varies benignly — the gate set encodes exactly that.
3. **Person matching** (the correctness core): a guest matches an expected
   person iff their casefolded token MULTISETS are equal
   (tokens(cognome) + tokens(nome) vs tokens(expected name)) — robust to
   slot-order flips ("KOVALCHUK IRYNA" == "IRYNA KOVALCHUK"), duplicate
   full names handled by multiset counting over persons, misses reported
   BY NAME in the scorecard.
4. **Artifacts.** Per invocation the harness writes
   `eval/scorecards/<date>-<label>.json` (machine record: per-list gates,
   metrics, per-run detail) + a rendered `.md` beside it (human record),
   and the dated raw captures. Nothing is auto-committed.
5. **Safety rails.** Live calls require an explicit `--live` flag; the
   default is dry/replay and prints the exact call count a live run would
   make. Any corpus path under `real-data/` is REFUSED — the holdout is
   never eval data (eval lists become tuning data by use; the holdout
   exists to stay the untouched final exam).
6. **Scope boundaries.** `eval/` is a new package; `run_llm.py` stays the
   untouched three-list demo; the `held_row`-hint prompt unfreeze is NOT
   this cycle — it is the first INTERVENTION this instrument will measure,
   afterward. Multi-model comparison is a `--model` flag away by
   construction (the caller is injected); no further machinery now.

## 3. The self-check that pins the expectations themselves

The expectations files are hand-authored and therefore the harness's own
weakest link — so the 15th suite runs the harness with each dev list's
HAND MAP injected as a zero-variance "caller" and requires ALL GATES
GREEN. If the hand map — our best-understood parse — cannot ace a list's
expectations, the expectations are wrong, and the suite says so before any
live run ever consumes them.

## 4. Test plan (test_eval_harness.py — suite 15) + touched surfaces

Deterministic end-to-end: replay callers on all four dev lists → the full
scorecard dict pinned exactly (gates all green; polish's junk disposition
and textmail's coverage recorded as the battery measured them). The
self-check of §3. Failure modes via injected callers: invalid-JSON caller
→ list FAILS with map_invalid, harness does not crash; a caller whose map
drops a person → recall gate fails AND the scorecard names the missing
person; an unstable pair of callers → stability metric surfaces the
disagreement. Matcher edges: order flip, duplicate names, extra guest.
The `real-data/` refusal. Counts: 14 → 15 everywhere (run_tests.sh,
CLAUDE.md ×3, README_START_HERE ×2) in the implementation commit.
Existing suites: byte-stable, zero assertion changes; engine untouched.

## 5. Cycle structure

Plan (this file) → implementation (`eval/harness.py`, `eval/run_eval.py`
CLI, `eval/expectations/{mix18,polish,park,textmail}.json`, suite 15,
counts) → docs commit (CLAUDE.md: the eval open item becomes "corpus
accumulation — the instrument is BUILT; every anonymized list that crosses
the desk joins `eval/`"; file map gains `eval/`; README status one line;
rev5 untouched — it is a sealed record) → patches → review. THE REVIEW
GAINS A NEW FINAL STEP, the division of labor made structural: after code
review, Claude Code runs the INAUGURAL live eval (`--live`, four lists,
K=2), inspects, and commits scorecard #1 as the first durable
live-quality record in the repo.

## 6. Out of scope (named)

The `held_row`-hint bundle (next cycle — instrument before intervention);
prompt changes of any kind; the ~20-list corpus itself (accumulates as
lists arrive); auto-commit machinery; multi-model campaigns; the app tiers.

## 7. Review outcome (user) + build-time adjustments

- **Call 1 approved as B**: expectations-file standard; hand-map bonus
  scoring on the dev four. Call 2 approved as drawn ("gate only the core
  parts of the product"); the `required_fields` per-list dial is built,
  DEFAULT EMPTY. Rails + the inaugural-live-eval review step approved.
- **Layout adjustment**: code lives FLAT at the repo root
  (`eval_harness.py`, `run_eval.py`) per house style — and a Python
  package named `eval` would shadow a builtin — while `eval/` holds DATA
  only (`expectations/`, `scorecards/`).
- **Dev expectations are BOOTSTRAPPED from the pinned hand parses**
  (persons verbatim from the parse fifteen suites + the live battery
  already established as ground truth), then frozen as static, human-
  auditable files; future lists are hand-authored from the document. The
  §3 self-check stays fully meaningful for those future files.
- **The engine gate, made precise**: the full path must run green on the
  live output — persist → version_completeness → PMS artifact → export →
  confirm → coverage `full`, delta empty. The completeness STATUS itself
  is a soft metric (an optional `completeness` expectations key), since
  junk disposition legitimately shifts polish's totals.
- **Core API**: `evaluate_list(rows, expectations, callers)` is the
  testable unit; the corpus manifest and CLI wrap it.
