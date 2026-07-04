# CLAUDE.md — project context for Soglia (rooming-list normalizer)

## What this is
Messy hotel guest-list document in → PMS-importable / Italian-police-portal
(Alloggiati Web) file out. LLM extraction at the boundary, deterministic code
downstream, human review in the middle. Pure Python, plain-`assert` tests.

## How to run the tests (do this before and after any change)
```
./run_tests.sh        # builds the golden file, runs all 14 suites, prints ALL GREEN (14/14)
```
Never edit a `.py` and assume it works — run this. All 14 must stay green.

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
- `stay.py` — `Stay` entity, deterministic held-capacity recognizer,
  `reconcile()` + `completeness_status()` (override-aware, §8.5.1/§8.5.2) +
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
- `soglia-demo.jsx` — standalone React UI mockup (not yet wired to anything).

## Current state (verified)
- Deterministic engine + SQLite: **built, 14/14 tests green.**
- **Not yet done:** the web server tier (Flask/FastAPI bridging UI↔engine), wiring the React demo to it, the Electron wrap.
- **Stage 1 IS validated live** on mix18/polish/park (checkpoint re-measure,
  2026-07-04: every live run's map reproduces the hand-map guests on mix18 and
  park — the dispatch floor absorbs park's missed held-row skip — and polish
  differs only by one junk header row the live map correctly treats as header).
  Fixture provenance, precisely: the TRACKED `llm_maps/*.json` are CURATED
  replay answers pinned byte-parity in test_llm_parser — NOT verbatim captures
  (park's fixture carries the Al.Mat skip no live run produced; live runs
  emitted `column_empty` instead). Raw live captures are LOCAL, regenerable,
  gitignored `*.live.json`. Still genuinely open: a textmail fixture (bundled
  with the `held_row`-hint contract unfreeze), **the ~20-list eval set** (the
  key empirical task), and the production model/provider choice — the caller
  is the swappable data-residency plug. Full record:
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

## SAFETY — this code handles passport data
- **Never commit real guest data or `soglia.db`.** `.gitignore` blocks them. Only anonymized samples in `data/` belong in git. Real lists go in `real-data/` (gitignored).
- The `.docx` reader needs a REAL Word file (a zipped OOXML package), not a text file. If a `.docx` ever reads as plain text, it's corrupt — re-export it.

## Style
No pytest, no frameworks added without asking. Small, plain, testable functions. Keep commits small and run `./run_tests.sh` before each.
