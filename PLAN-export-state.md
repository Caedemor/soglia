# PLAN — export-state tracking + delta export (commit 2 of addendum §8.5.8)

Branch: `export-state` off main `d3a31d8`. Ground truth read in full before
design: addendum §8.5.1, §8.5.4–§8.5.8; handoff §13 (esp. 13.2 arrival
stamping, 13.5 canonical-list-is-the-product, 13.8 reject-loop, 13.9
idempotency); the §8.1 mermaid SUBMISSION / SUBMISSION_RESULT shapes; the
as-built storage schema. STATUS: design brief — awaiting approval, no code yet.

## 1. What the doc settled (no forks here)

- A PMS export IS a `SUBMISSION` (`target ∈ {alloggiati, pms}`), lifecycle for
  pms: `generated` (file exists, `artifact_hash` set) → `export_confirmed` →
  `superseded`. `idempotency_key` guards double-clicks (§13.9);
  `submitted_arrival_date` is where §13.2's submit-time stamping lives.
- `SUBMISSION_RESULT(outcome = exported_unverified)` per included guest —
  never `accepted`; the PMS reports nothing, so the record is *intent the
  human confirmed*. Only a confirmed export flips guests to exported.
- **Export coverage** (`none | partial | full`) is computed over NAMED guests
  from confirmed results. **The delta** = un-exported named guests — pure
  set membership, shown first; "export everything" always offered; re-export
  appends and supersedes, never deletes. History is the audit trail.
- `GUEST` unchanged — export state is read off results, one source of truth.
- STUBBED by §8.5.8's own decree: `person_key` cross-version diff (so the
  "corrected name on Wednesday" case is out of scope — see call 7) and the
  Alloggiati partial/reject result loop.

## 2. The seven design calls (each vetoable)

1. **The commit-2 / commit-4 seam.** The `generated → export_confirmed`
   transition ships NOW as a bare state machine — without it, coverage is
   uncomputable and commit 2 isn't "independently testable." Commit 4 adds
   what §8.5.5 actually specifies: the `export_confirm` json
   `{actor, ts, guest_count}` audit record and the red-gate UX. The nullable
   `export_confirm` column is created now (empty until 4) to avoid a
   migration later.
2. **Superseded ≠ invalidated.** Appending a new pms SUBMISSION marks the
   prior one `superseded` (doc-literal), but results are write-once facts:
   coverage queries results directly, so guests confirmed under a
   now-superseded export STAY covered. Otherwise the stepfather arithmetic
   collapses (the 25 would un-export the moment the 5 are exported).
   "Superseded" means *no longer the newest hand-off*, nothing more.
3. **Manifest at generation — flagged deviation from §8.5.4's letter.** The
   confirm must confirm exactly the generated file's guest set (recomputing
   the delta at confirm time would be racy). So result rows are created at
   GENERATION with `outcome = ''` (a manifest) and upgraded to
   `exported_unverified` at confirm. The letter says results are "written at
   export_confirmed" — read as: *outcomes* are written at confirm. Coverage
   queries `outcome = exported_unverified`, so manifests never count.
4. **The v1 PMS artifact is a canonical CSV.** No PMS template exists in any
   doc, and §13.5 says it outright: "the canonical list is the product; every
   PMS output is a cheap row-operation off it." Deterministic bytes (stable
   columns, sorted by guest idx, \n endings) → stable `artifact_hash`. Held
   stays ARE included as booking rows (`names_pending`, pax_expected,
   verbatim) per §8.5.7's logistics lens. `unrecognized` stays are EXCLUDED —
   they are attention items, not bookings; they gate completeness, not the
   hand-off. Bedzzle/Opera column templates are later adapters.
5. **The delta ignores `is_submittable`.** PMS is the logistics lens: a named
   guest missing a birthdate is still a real booking, and §8.5.4's delta is
   defined over *named* guests, not submittable ones. Reds gate the export
   ACTION (commit 4), never the set math. Alloggiati submittability keeps
   gating the tracciato exactly as today.
6. **Alloggiati generation-recording included, minimal.** One function
   records an alloggiati SUBMISSION (`status = pending`, artifact_hash of the
   tracciato bytes, `submitted_arrival_date` stamped at submission — §13.2
   honored, re-resolution caveat §13.9 noted). The verdict/receipt loop stays
   stubbed. Cheap, and it keeps "what hand-offs has this guest been part of"
   in one place as §8.5.4 intends.
7. **Delta identity = `guest.id` within a version.** Cross-version matching
   is `person_key`, stubbed by decree — so in v1, uploading a corrected
   VERSION starts a fresh export history for that version. Stated as the
   known ceiling, not hidden: the honest failure is "delta offers everyone
   again after a re-upload," never "silently deduped wrong."

## 3. Blast radius

- `export.py` — NEW: `Submission` / `SubmissionResult` dataclasses;
  `build_pms_csv(guests, stays) -> str` (pure, deterministic, golden-style
  testable). No SQL here.
- `storage.py` — two `CREATE TABLE IF NOT EXISTS` (submission,
  submission_result; INTEGER PKs per house style — the mermaid's uuids are
  a doc-level idiom); `_SUB_COLS`/`_RES_COLS` with the same import-time
  drift asserts Guest and Stay have; workflow functions (all conn-first,
  SQL stays in this file): `load_guests_with_ids`, `record_pms_export`
  (generation: submission row + manifest + idempotency dedupe + supersede
  prior), `confirm_export`, `record_alloggiati_submission`,
  `export_coverage`, `pms_delta`, `load_submissions`. No ALTERs — new
  tables only, so legacy migration is free.
- ZERO changes: `parser.py`, `stay.py`, `validate.py`, `maps.py`,
  `tracciato.py`/golden (tripwire), `llm_parser.py` + fixtures,
  `orchestrator.py` — the two axes deliberately live in different places:
  completeness is a property of the PARSE (`ListResult.completeness()`),
  export coverage is a property of the RECORD (`storage.export_coverage`).
- Docs: CLAUDE.md (file map + current state + 12/12 counts),
  README_START_HERE (12/12 ×2), run_tests.sh (+test_export).

## 4. Test plan (test_export.py, the 12th suite)

Generation: submission + manifest rows written, artifact hash deterministic
across runs, double-generate with identical inputs returns the SAME
submission (idempotency), new generation supersedes the prior pms export.
Confirm: outcomes flip to `exported_unverified`, coverage recomputes, prior
confirmed export's guests remain covered (call 2 pinned). Coverage walk on
park: none → confirm a subset → partial → export delta + confirm → full.
Stepfather arithmetic on textmail: confirm 42 of 47 → delta offers exactly
the 5. **The flagship — axis orthogonality:** textmail reaches
`export_coverage = full` while completeness stays `awaiting_completion`
(2 held pax) — the §8.5.1 two-axis banner, proven in one assert. Artifact:
held stays present as booking rows, unrecognized rows absent, red
(non-submittable) named guests present in the delta (call 5 pinned).
Alloggiati recording stamps `submitted_arrival_date`. Round-trip + legacy
migration (tables appear via init_db on an old DB). All existing suites:
byte-stable, zero assertion changes.

## 5. Out of scope (named, so nothing silently sprawls)

Audit records + red gates (commit 4); supplements (commit 3); Alloggiati
verdict ingestion + receipts; `person_key`; PMS-specific templates; any UI.

## 6. Review outcome (user, pre-implementation)

- **#4 amended:** the real Bedzzle import template has been requested from
  the field (stepfather) and is incoming. Build proceeds NOW with the
  canonical CSV; the builder seam is made explicit — `record_pms_export`
  takes the artifact TEXT as an argument, so a Bedzzle-shaped builder lands
  later (fixup if during review, adapter commit if after) with zero
  machinery change. The template doubles as evidence for the queued
  room-type-column follow-up.
- **#5 confirmed** with the lens split stated: PMS export needs no override
  ever in commit 2 (commit 4 adds a proceed-able warning); alloggiati keeps
  today's per-row behavior (reds sit out of the tracciato; force-include
  override is commit 4). Nothing hard-blocks (§13.7).
- **Calls 1, 2, 3, 6, 7:** approved by silence.
- **Two decisions surfaced during implementation design, added here:**
  (a) the delta/coverage denominator is ALL persisted guests of the version,
  including skip-flagged junk — excluding them silently would drop a
  wrongly-skipped REAL guest from the hand-off (the §8.5.7 sin); junk in the
  delta fails LOUD (visible row in the export) and review-resolution removes
  it from the denominator naturally when that lands. Pinned in tests.
  (b) confirming a SUPERSEDED submission is REFUSED with a clear error — a
  newer file exists; confirming a stale artifact would record a belief about
  bytes the human probably didn't import. Pinned in tests.

STATUS: approved — implementation follows in the next commit.
