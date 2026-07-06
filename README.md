# Soglia

Rooming-list normalizer for Italian hotels: a messy guest-list document goes
in (docx / xlsx / plain-text paste, any layout), a PMS-importable file and an Alloggiati Web
(police-portal) schedine file come out — with a human review step in the
middle and nothing invented by software.

One architectural rule: the LLM reads the document ONCE at the boundary and
emits a column map (stage 1); everything downstream is deterministic,
testable Python (stage 2 onward). The model never writes output files, never
picks code-table codes, never talks to the portal.

Status: **the engine is complete** — all four §8.5.8 build commits plus the
dispatch floor (`./run_tests.sh` — 15 suites): STAY/held-capacity
reconciliation, no row with content ever vanishes, export-state tracking
with delta-first re-export, supplement accumulation, and the two audited
human assertions (mark-complete override; confirm-export). Stage 1 is
validated LIVE against the model on the dev lists (fixtures are captured
output). The stage-1 eval instrument is in (`run_eval.py` — the corpus accumulates
as anonymized lists arrive). Next: the app tiers (server, review UI + edit
loop, wrapper).
Current-state record: docs/handoff-rev5.md (dated postscript for commit 4).

Start with [README_START_HERE.md](README_START_HERE.md) (first-time setup)
and [CLAUDE.md](CLAUDE.md) (working state + invariants). Design records live
in [docs/](docs/); the addendum was the authoritative spec for the (now
complete) engine build and remains the reference for its semantics. This code handles passport data: never commit real guest lists or
`soglia.db` — only the anonymized samples belong in `data/`.
