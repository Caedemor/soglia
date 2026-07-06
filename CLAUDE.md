# CLAUDE.md — project context for Soglia (rooming-list normalizer)

## What this is
Messy hotel guest-list document in → PMS-importable / Italian-police-portal
(Alloggiati Web) file out. LLM extraction at the boundary, deterministic code
downstream, human review in the middle. Pure Python, plain-`assert` tests.

## How to run the tests (do this before and after any change)
```
./run_tests.sh        # builds the golden file, runs all 15 suites, prints ALL GREEN (15/15)
```
Never edit a `.py` and assume it works — run this. All 15 must stay green.

## The one architectural rule, never break it
The LLM touches data exactly once, at the boundary (messy doc → a `ColumnMap`).
Everything after that is deterministic, testable code. The LLM never writes a
final file, never picks a code-table code, never talks to the portal.
- **Stage 1** (`llm_parser.py`): model reads headers+sample rows → emits a `ColumnMap` (JSON). Swappable caller: `anthropic_caller` (live), `replay_caller` (fixtures), or a local model.
- **Stage 2** (`parser.py`): pure transcriber, walks every row using the map. No judgement, no meaning-cleaning.

## Hard invariants (tests guard these — do not "fix" them away)
- **No silent truncation.** Over-length surname/name/doc-number is a RED issue, never chopped. (`tracciato.py`, `validate.py`)
- **Verbatim means verbatim.** Source typos are preserved; the desk reconciles at check-in. Never auto-correct names.
- **Null is a valid answer.** Missing fields stay missing and surface as issues; never guessed-to-fill.
- **Inference is advisory only** (`infer.py`): suggests sex / list-level citizenship for EMPTY fields, capped "yellow", never overwrites. Deleting `infer.py` must not break the base.
- **A row is not a guest.** Twin rows carry two people; counts are PAX-aware.
- **Nothing vanishes unreviewably.** Junk rows emit-and-flag (`skip_flag`);
  held "N pax" rows become `names_pending` Stays carrying the source cell
  text verbatim; rows the map cannot see AT ALL become `unrecognized` Stays
  that BLOCK completeness until a human looks (addendum §8.5.7).

## File map
- `tracciato.py` — 168-char Alloggiati formatter + `Guest`. Golden-file tested.
- `validate.py` — the red-issue gate (`is_submittable`).
- `parser.py` — generalized stage-2 transcriber (map-driven; five-way row
  dispatch: guests / held Stays / emit-and-flag / `unrecognized` residue /
  true blank).
- `stay.py` — `Stay` entity, deterministic held-capacity recognizer
  (`held_pax`), `reconcile()` + `completeness_status()` (override-aware, §8.5.1/§8.5.2) +
  `derive_status()` (the supplement counter rule).
- `maps.py` — file readers (`.docx` tables, `.xlsx` with merged-cell fill-down, `.txt` strict-TSV email paste) + hand-written `ColumnMap`s for the 4 sample lists. Data path = `./data/` (relative).
- `llm_parser.py` + `llm_maps/*.json` — stage-1 plug + replay fixtures.
- `orchestrator.py` — `process_list(parser, stays=…) → ListResult` (reds,
  suggestions, reconciliation, completeness via stays, tracciato).
- `infer.py` — decoupled advisory inference.
- `storage.py` — SQLite persistence (`connect` → `init_db` →
  `save_list`/`load_list`; stays: `save_list(..., stays=)` / `load_stays`) +
  the export-state workflow (§8.5.4): `record_pms_export` → `confirm_export`,
  `pms_delta`, `export_coverage`, `record_alloggiati_submission` — and the
  supplement workflow (§8.5.3): `apply_supplement` + `guest_lineage`; and
  the §8.5.5 assertions: `mark_complete_override` / `version_completeness`.
- `export.py` — PMS artifact (canonical CSV, injectable builder — Bedzzle
  template incoming lands as another builder) + `Submission`/`SubmissionResult`.
- `data/` — four ANONYMIZED sample lists (Ukrainian .docx 39, Polish .xlsx 48, Italian .xlsx 23, text-mail TSV 47).
- `eval_harness.py` + `run_eval.py` — the stage-1 eval instrument
  (PLAN-eval-harness.md): hard gates (map compiles, 100% person recall,
  held arithmetic, required_fields dial, ENGINE PATH green) vs soft
  metrics (junk disposition, role, coverage, stability, hand-map parity).
  Ground truth: `eval/expectations/*.json` (committed); scorecards:
  `eval/scorecards/` (written by the harness, COMMITTED by the runner);
  raw captures: dated gitignored `*.live.json`. `--live` is opt-in;
  `real-data/` is refused.
- `soglia-demo.jsx` — standalone React UI mockup (not wired to anything;
  predates the STAY/export engine — visual inspiration for the review-UI
  cycle, not a spec).

## Current state (verified)
- Deterministic engine + SQLite: **built, 15/15 tests green.**
- **Not yet done:** the app tiers — a thin web server (Flask/FastAPI
  bridging UI↔engine), the review UI + edit loop (the jsx mockup is
  inspiration, not spec), export buttons over the commit-2/4 machinery,
  the wrapper.
- **Stage 1 IS validated live** on ALL FOUR dev lists (checkpoint re-measure +
  same-day closing battery,
  2026-07-04: every live run's map reproduces the hand-map guests on mix18 and
  park — the dispatch floor absorbs park's missed held-row skip — and polish
  differs only by one junk header row the live map correctly treats as header;
  textmail's FIRST live pass: all 47 guests, the out-of-window trailer caught
  by the dispatch floor — rev5 §8).
  Fixture provenance, precisely: the TRACKED `llm_maps/*.json` are CURATED
  replay answers pinned byte-parity in test_llm_parser — NOT verbatim captures
  (park's fixture carries the Al.Mat skip no live run produced; live runs
  emitted `column_empty` instead). Raw live captures are LOCAL, regenerable,
  gitignored `*.live.json`. Still genuinely open: a textmail fixture (bundled
  with the `held_row`-hint contract unfreeze — the FIRST intervention the
  eval instrument will measure), **the eval corpus** (the instrument is
  BUILT: `eval_harness.py` + `run_eval.py` + suite 15; lists accumulate as
  they arrive — an expectations file per list, minutes each; live runs and
  scorecard commits happen ONLY on the machine with the key), and the
  production model/provider choice — the caller is the swappable
  data-residency plug. Full record:
  [docs/handoff-rev5.md](docs/handoff-rev5.md) §2 + §7.
- **Incomplete-list / supplement / dual-target-export work** (design ground
  truth: [docs/rooming-list-schema-rev3-addendum-A.md](docs/rooming-list-schema-rev3-addendum-A.md)):
  **all four §8.5.8 build commits are in code — the ENGINE IS COMPLETE.**
  Commit 1: the `STAY` foundation
  (identity/stay split, twin = one `STAY` + two `GUEST`s, held capacity +
  reconciliation). Park reconciles 41 expected / 23 named / 18 pending →
  `awaiting_completion`; design rationale (esp. held `pax_expected` = name-slot
  capacity, NOT the placeholder text-N) is in [PLAN-stay-foundation.md](PLAN-stay-foundation.md).
  Commit 2 adds `SUBMISSION(target=pms)` with `generated → export_confirmed
  (→ superseded)`, manifest-then-outcomes results, delta-first non-destructive
  re-export, `export_coverage` (the second §8.5.1 axis — orthogonality to
  completeness is pinned in test_export), and minimal alloggiati recording
  with §13.2's submit-time arrival stamp; design + the seven calls in
  [PLAN-export-state.md](PLAN-export-state.md). Commit 3 adds
  `apply_supplement` (§8.5.3): a supplement is a NEW version
  (`relation_to_prior='supplement'`) — prior guests carried with
  `guest_lineage` receipts (export facts survive the carry; NOT person_key),
  the held pool merged into ONE coarse block stay, names attached by
  counter, mismatch tolerated ('over' reachable); the Monday→Wednesday
  story is pinned end-to-end in test_supplements. Design:
  [PLAN-supplements.md](PLAN-supplements.md). Commit 4 adds the two §8.5.5
  audited assertions: `mark_complete_override` (per-version json record —
  `complete_by_override`; a supplement resets the assertion) and
  `confirm_export(…, actor=)` recording `{actor, ts, guest_count}`; the
  regeneration corner is fixed (§13.9 dedupe scoped to non-superseded,
  suffixed keys). Red gates are UI confirmations over facts the engine
  already exposes; per-field `origin=override` waits for `field_meta` + the
  review UI. Design: [PLAN-audit-override.md](PLAN-audit-override.md).
  **Next: the app tiers** (upload shell, review UI + edit loop, exports).
  Full current-state record: [docs/handoff-rev5.md](docs/handoff-rev5.md)
  (dated postscript covers commit 4).

## Known open items (small, deliberately deferred)
- Held-capacity edge (see comment in `stay.py`): a cell mixing a full name
  with a count classifies as held; room-type-column mapping is the fix.
- **Stage-1 `held_row` hint (the deliberate contract unfreeze):** map-authored
  held classification, same trust model as `skip_row` — a HINT producing
  review-visible held stays, never silent ones. Ships as one commit: stage-1
  prompt + ALL fixtures + a hand-authored `llm_maps/textmail.json`. The
  dispatch floor stays the guarantee underneath.
- **Polish "Driver N" rows:** decide whether guard-red placeholder guests
  should become held pax-1 stays (polish currently reads complete-with-reds:
  the completeness axis says done while 2 drivers are unnamed; the red gate is
  what blocks it today). Moves polish counts across four suites — needs its
  own blast radius.

## Collaboration protocol (how this repo is actually worked)

Three roles, proven over the engine build (July 2026):
- **Web-chat Claude (the sandbox):** designs and builds every cycle in a
  fresh clone of origin — hermetic, NO API key, never runs live. Delivers
  work as `git format-patch` files plus a scripted review prompt.
- **Claude Code (the machine):** applies patches (`git am`), reviews
  adversarially, runs everything LIVE (stage-1 calls, eval campaigns),
  pushes branches, executes scripted fixup-and-merge prompts.
- **The user** arbitrates contested review calls and owns the field inputs
  (new lists, the Bedzzle template) and API spend.

The cycle: read the governing doc VERBATIM (never from memory) → commit a
`PLAN-*.md` design brief → STOP for the user's pass → build → full suite +
demos → format-patch + pristine-clone verify (tree-hash compare) →
adversarial review on the machine → branch pushed → findings arbitrated →
scripted fixups → `--ff-only` merge → the sandbox byte-verifies origin →
branch deleted. Main is never force-pushed and never red.

Records discipline: pushed commit messages are never rewritten. PLAN files
amend before merge only; afterward, dated postscripts. `/docs` revisions
are sealed (additive dated postscripts only). Scorecards are committed by
the runner as an explicit act; raw captures stay gitignored.

Process rules (each paid for at least once):
- This file is read TOP TO BOTTOM in every doc pass — never anchor-grepped
  (three stale-line escapes taught this).
- Multi-line shell: `set -e` + NEWLINE-separated commands, never
  `&&`-chains across lines — `set -e` exempts `&&`-list members by design
  (three false-commit incidents taught this).
- Bulk edits go through anchor-asserted replacement (`count == 1`): a
  wrong anchor must fail loudly, never skip silently.
- Suite-count surfaces: `run_tests.sh` + this file ×3 + README_START_HERE
  ×2 + the README status — swept in the SAME commit as any suite add.
- The user's machine: use `/usr/bin/git` (Homebrew git EPERMs there); a
  background poller leaves stale `.git/index.lock` — remove it, move on.
- The holdout (`real-data/`) is sealed for EVERYONE; the eval corpus is
  tuning data by definition and never includes it.
- A fresh sandbox session: clone origin, read this file FULLY, then
  `docs/handoff-rev5.md` (§1–§8), then the newest `PLAN-*.md`.

## SAFETY — this code handles passport data
- **Never commit real guest data or `soglia.db`.** `.gitignore` blocks them. Only anonymized samples in `data/` belong in git. Real lists go in `real-data/` (gitignored).
- The `.docx` reader needs a REAL Word file (a zipped OOXML package), not a text file. If a `.docx` ever reads as plain text, it's corrupt — re-export it.

## Style
No pytest, no frameworks added without asking. Small, plain, testable functions. Keep commits small and run `./run_tests.sh` before each.
