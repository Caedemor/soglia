# Soglia — handoff, rev. 5 (July 4, 2026)

**This is the current-state record.** Reading order for the doc set: this file
(state) → `rooming-list-schema-rev3-addendum-A.md` (authoritative spec for the
remaining build) → `rooming-list-schema-rev3-draft.md` (schema; two field
names superseded by addendum §8.5.6) → `handoff-rev4.md` (historical — its
"what's built" claims describe June, not now). The per-cycle design rationale
lives in the committed `PLAN-*.md` files at the repo root; CLAUDE.md is the
working memory (invariants, open items, safety rules).

## 1. What is built and green (13 suites, `./run_tests.sh`)

The deterministic engine now covers §8.5.8 build commits **1, 2 and 3 of 4**,
plus a safety commit (1.5) the textmail list forced:

- **Stage 2 (`parser.py` + `stay.py`)** — map-driven transcription with a
  five-way row dispatch: guests / in-slot held stays / emit-and-flag junk /
  residue (held or `unrecognized`) / true blank. The categorical floor:
  a row with ANY content the map cannot see becomes an `unrecognized` stay
  that blocks completeness — a vocabulary miss costs a human a glance, never
  a silent false-complete. Held `pax_expected`: slot capacity in-slot
  (park's text restates block totals — text-sum 161 vs the true 18), text-N
  for slotless residue ("+ 2 autisti" → 2). Twins are one `STAY` + two
  `GUEST`s. (PLAN-stay-foundation, PLAN-dispatch-floor.)
- **Reconciliation (§8.5.2)** — per-stay pending/overage summed;
  `completeness_status` = pending 0 AND unrecognized 0. Overage is advisory,
  never blocking; `STAY.status` spans `names_pending | complete | over |
  unrecognized` ('over' reachable via supplements).
- **Export state (§8.5.4, commit 2)** — `SUBMISSION(target ∈ {alloggiati,
  pms})`; pms lifecycle `generated → export_confirmed (→ superseded)`;
  write-once `SUBMISSION_RESULT(outcome=exported_unverified)` at confirm is
  the ONLY thing that flips a guest to exported; idempotency-keyed
  generation; delta-first non-destructive re-export; `export_coverage`
  (`none | partial | full`). Superseded ≠ invalidated. Artifact builders are
  injectable (`export.py` — canonical CSV now; the Bedzzle template is
  requested from the field and lands as another builder). §13.2's
  submit-time arrival stamp is recorded on the alloggiati submission.
  (PLAN-export-state.)
- **Supplements (§8.5.3, commit 3)** — `apply_supplement` builds a NEW
  version (`relation_to_prior = 'supplement'`): prior guests carried forward
  with `guest_lineage` receipts, the held pool merged into ONE coarse block
  stay (verbatims preserved), supplement names attached to the block,
  counter-derived stored status, mismatch tolerated both directions. Export
  facts survive the carry through lineage — the §8.5.4 stepfather works
  (25 exported + 5 supplement → the delta offers exactly the 5), through
  chains. Lineage is a receipt of our own deterministic copy — explicitly
  NOT the stubbed `person_key` (fuzzy matching of independent uploads).
  The Monday→Wednesday story is end-to-end real and pinned as the flagship
  test. (PLAN-supplements.)
- **The safety floor beneath everything** — non-destructive skips
  (emit-and-flag), the name-plausibility guard as backstop, golden-file
  byte identity on the Alloggiati formatter, verbatim preservation, import-
  time schema/dataclass drift asserts, in-place DB migrations.

Four real anonymized dev lists exercise all of it: mix18 docx (39), polish
xlsx (48 + 7 flagged), park xlsx (23 + 9 held = 18 pax), text-mail TSV
(47 + held trailer 2). The holdout set stays sealed.

## 2. Stage 1 — the record, corrected

rev4 framed the live stage-1 call as "not yet run." **That is stale and was
never carried forward correctly: stage 1 HAS run live, multiple times,
against the Claude API** (~$2 total for several full passes — the per-list
mapping cost is cents, and stage 1 runs once per list by design). The
`llm_maps/*.json` fixtures are CAPTURED live model output — their
`review_notes` are the model's own prose observations — and
`test_llm_parser` pins live-map parity against the hand maps on three lists.
Park's famously missing held-row skip rule is a real live-model blind spot,
which the deterministic layers were then built to catch.

Still open on this front: `textmail` has no fixture (stage 1 has never seen
it) — bundled with the `held_row`-hint contract unfreeze below; and the
production model/provider choice is deliberately unmade — the caller is the
swappable data-residency plug (`llm_parser.py`), so this is configuration,
not architecture.

## 3. Decisions recorded here (closing old open items)

- **Birth-date plausibility:** the code's rolling 120-year cap is CANONICAL.
  §7.4's fixed "1920–2026" was an era-bound draft approximation; do not
  align code to it.
- **2-digit years** are never expanded to a century. `norm_dotted_date`
  leaves them verbatim and the validator reds the format — a human decides.
- `_mix18_role` is guarded; a short row takes the default role.

## 4. Open items (live list maintained in CLAUDE.md)

Stage-1 `held_row` hint (prompt + all fixtures + a textmail fixture, one
commit; the dispatch floor stays the guarantee underneath) · polish
"Driver N" reclassification decision · commit-4 UX: regeneration-corner
confirm flow + scoping the §13.9 dedupe to non-superseded submissions ·
room-type-column mapping (fixes the name+count held edge and held singles)
· `person_key` + correction diffing (v2) · `SOURCE_DOCUMENT` entity +
`version_no` (app tier) · Bedzzle template → second artifact builder +
room-type evidence.

## 5. What remains

**Commit 4 (§8.5.5):** override + audit — `complete_by_override` with
`{actor, ts, pending_at_override, reason}`, `export_confirm` json
`{actor, ts, guest_count}`, red gates as proceed-able warnings (§13.7:
nothing hard-blocks). Then the engine is done and the **app tiers** begin:
upload shell, the review surface (`GuestResult` is already UI-shaped), the
edit loop (needs its own design cycle — edits-as-corrected-version,
provenance), export buttons on the commit-2/3 machinery. The engine stays
the product; the UI stays thin.
