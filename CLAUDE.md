# CLAUDE.md — project context for Soglia (rooming-list normalizer)

## What this is
Messy hotel guest-list document in → PMS-importable / Italian-police-portal
(Alloggiati Web) file out. LLM extraction at the boundary, deterministic code
downstream, human review in the middle. Pure Python, plain-`assert` tests.

## How to run the tests (do this before and after any change)
```
./run_tests.sh        # builds the golden file, runs all 10 suites, prints ALL GREEN (10/10)
```
Never edit a `.py` and assume it works — run this. All 9 must stay green.

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

## File map
- `tracciato.py` — 168-char Alloggiati formatter + `Guest`. Golden-file tested.
- `validate.py` — the red-issue gate (`is_submittable`).
- `parser.py` — generalized stage-2 transcriber (map-driven).
- `maps.py` — file readers (`.docx` tables, `.xlsx` with merged-cell fill-down) + hand-written `ColumnMap`s for the 3 sample lists. Data path = `./data/` (relative).
- `llm_parser.py` + `llm_maps/*.json` — stage-1 plug + replay fixtures.
- `orchestrator.py` — `process_list(parser) → ListResult` (reds, suggestions, reconciliation, tracciato).
- `infer.py` — decoupled advisory inference.
- `storage.py` — SQLite persistence (`connect` → `init_db` → `save_list`/`load_list`).
- `data/` — three ANONYMIZED sample lists (Ukrainian .docx 39, Polish .xlsx 48, Italian .xlsx 23).
- `soglia-demo.jsx` — standalone React UI mockup (not yet wired to anything).

## Current state (verified)
- Deterministic engine + SQLite: **built, 10/10 tests green.**
- **Not yet done:** the web server tier (Flask/FastAPI bridging UI↔engine), wiring the React demo to it, the Electron wrap.
- **Never validated live:** the stage-1 LLM call has only ever run against saved fixtures (`replay_caller`). The `ColumnMap`s in `maps.py` are hand-written stand-ins. Running stage 1 against a live model on real documents — and building the ~20-list eval set — is the key open empirical task.
- **Incomplete-list / supplement / dual-target-export work:** design ground truth is [docs/rooming-list-schema-rev3-addendum-A.md](docs/rooming-list-schema-rev3-addendum-A.md) — forward-looking spec (`STAY` held capacity, `SUBMISSION target=pms`, two-axis completeness/export state) that is **not yet in code**; treat it as authoritative for that build, not as a description of current state.

## SAFETY — this code handles passport data
- **Never commit real guest data or `soglia.db`.** `.gitignore` blocks them. Only anonymized samples in `data/` belong in git. Real lists go in `real-data/` (gitignored).
- The `.docx` reader needs a REAL Word file (a zipped OOXML package), not a text file. If a `.docx` ever reads as plain text, it's corrupt — re-export it.

## Style
No pytest, no frameworks added without asking. Small, plain, testable functions. Keep commits small and run `./run_tests.sh` before each.
