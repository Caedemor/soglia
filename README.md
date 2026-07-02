# Soglia

Rooming-list normalizer for Italian hotels: a messy guest-list document goes
in (docx/xlsx, any layout), a PMS-importable file and an Alloggiati Web
(police-portal) schedine file come out — with a human review step in the
middle and nothing invented by software.

One architectural rule: the LLM reads the document ONCE at the boundary and
emits a column map (stage 1); everything downstream is deterministic,
testable Python (stage 2 onward). The model never writes output files, never
picks code-table codes, never talks to the portal.

Status: deterministic engine + SQLite persistence + STAY / held-capacity
reconciliation built and green (`./run_tests.sh` — 11 suites). The live
stage-1 extraction and the app tiers (server, UI, wrapper) are not built yet.

Start with [README_START_HERE.md](README_START_HERE.md) (first-time setup)
and [CLAUDE.md](CLAUDE.md) (working state + invariants). Design records live
in [docs/](docs/); the addendum is authoritative for the incomplete-list
build. This code handles passport data: never commit real guest lists or
`soglia.db` — only the anonymized samples belong in `data/`.
