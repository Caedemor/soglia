# PLAN — override + audit: the two human assertions (commit 4 of §8.5.8)

Branch: `audit-override` off main `8e40f7a`. Ground truth read verbatim:
addendum §8.5.5 (the assertions), §8.5.6 (json shapes), §8.5.4 (confirm
lifecycle); handoff §13.7 via §8.2 (origin=override philosophy; red gates as
proceed-able warnings, never walls), §13.9 (idempotency intent). STATUS:
design brief — awaiting approval, no implementation yet.

## 1. What the doc settled (no forks)

- Both actions are "§13.7 applied ABOVE field level": recorded assertions,
  never boolean flips. "The record — not the warning — is the point."
- **Mark-complete-despite-pending** → `complete_by_override`, json
  `{actor, ts, pending_at_override, reason}` on LIST_VERSION.
- **Confirm-export** → json `{actor, ts, guest_count}` on SUBMISSION —
  logging WHOSE belief and WHEN, because a belief is the honest ceiling
  without a PMS API.
- Red gates are UI confirmations in front of the assertions ("this list is
  INCOMPLETE — N guests still unnamed. Mark complete anyway?"). The engine's
  job is the facts feeding them (reconciliation already provides N) and the
  records behind them — nothing hard-blocks (§13.7).
- **Out of scope by the docs' own coupling:** per-FIELD `origin=override`
  (force-including red guests in the tracciato) lives in `field_meta`, which
  the handoff binds to the review UI. §8.5.5 is explicitly above field
  level; the tracciato and validate are untouched this commit.

## 2. The design calls (each vetoable)

1. **`actor` is REQUIRED on both assertions** — an unattributed audit record
   is hollow, and the record is the product. `confirm_export(conn, sid, *,
   actor)` is therefore a BREAKING signature change to commit 2's function;
   every callsite (test_export ×6, test_supplements ×4) is updated in the
   same commit and listed in §4. `mark_complete_override(conn, vid, *,
   actor, reason)` is born requiring both.
2. **Override refusals + per-version semantics.** Overriding an
   already-complete version is refused (nothing to vouch for); overriding
   twice is refused (the state is already `complete_by_override`; the first
   record stands). The override lives ON the version: a later supplement
   creates a NEW version with NO override — new facts, new responsibility —
   pinned in tests. Versions remain the history mechanism.
3. **Json extensions, flagged.** Field name `ts` per §8.5.6 (§8.5.5's prose
   says "timestamp" — the entity spec wins). Beside the spec'd
   `pending_at_override`, the record gains `unrecognized_at_override` — the
   dispatch floor postdates §8.5.5, and an override that vouched past an
   unrecognized row must say so (same extension precedent as reconcile's
   `unrecognized` key). `json.dumps(..., sort_keys=True)` for stable bytes.
4. **Computed truth beats the label.** `completeness_status(rec,
   override=False)` returns `complete` when genuinely complete (the json
   remains as history), `complete_by_override` only while actually
   incomplete-but-vouched. Pure-function signature stays backward
   compatible; parse-side `orchestrator.completeness()` is untouched; the
   persisted-side twin `version_completeness(conn, vid)` marries
   reconciliation + the override column and is what a UI will call.
5. **The regeneration corner, fixed as queued** (CLAUDE.md open item →
   resolved): on an idempotency-key collision with a SUPERSEDED submission,
   `record_pms_export` mints a fresh submission under a deterministic
   suffixed key (`<base>|r2`, `|r3`, …) — regeneration lineage auditable in
   the key itself. True double-clicks (collision with a NON-superseded
   submission) dedupe exactly as before; the confirm-a-superseded refusal
   stays as defense-in-depth.
6. **`Submission.export_confirm` comment updated** ("commit 4 fills" →
   filled) — the column itself has existed since commit 2, by design.

## 3. Cycle structure — the finale's close-out

Plan commit (this file) → implementation + `test_audit.py` (suite 14, counts
14/14 same-commit) → closing docs commit: CLAUDE.md current-state flips to
**4 of 4 — the engine is COMPLETE**; the regeneration open item comes out;
README status: all four commits in, app tiers next. **One flagged /docs
touch:** `handoff-rev5.md` gains a short, DATED postscript (`## 6.
Postscript`) recording commit 4 — additive only, original text untouched.
Rationale: rev5 is the designated entry-point record; letting its "what
remains" section rot on arrival recreates the rev4 disease the file exists
to cure. A full rev6 for one commit would be ceremony over substance.

## 4. Test plan (test_audit.py) + every touched assertion

Mark-complete: refuse on already-complete and on double-override; the json
records actor/ts/pending (+unrecognized) faithfully — including the
unrecognized-only case (pending 0, floor blocking, override vouches past
it); `version_completeness` returns `complete_by_override`; a supplement
AFTER an override yields a fresh version that is honestly `awaiting` again
(call 2 pinned); a version that becomes genuinely complete reports
`complete` while the json survives as history (call 4 pinned).
Confirm-export: json `{actor, ts, guest_count}` written at confirm,
guest_count == manifest size; pre-commit-4 submissions' empty json
unaffected; refusals from commit 2 all intact. Regeneration corner: the
EXACT commit-2 review sequence (generate A → generate B → regenerate
A-bytes) now mints a fresh, confirmable submission with key `<base>|r2`;
double-click still dedupes. Migration: a commit-3-era DB (no
completeness_override column) upgrades in place.

Touched existing assertions, old → new: `confirm_export(c, sid)` →
`confirm_export(c, sid, actor="...")` at ten callsites across test_export
and test_supplements — signature only, zero behavioral assertions change.
Everything else: byte-stable.

## 5. Out of scope (named, final list)

Per-field `origin=override` + `field_meta` (review-UI cycle);
`person_key`/correction diffing (v2); `SOURCE_DOCUMENT`/`version_no` (app
tier); stage-1 `held_row` hint + textmail fixture + the ~20-list eval set;
polish Driver decision; Bedzzle builder (template still incoming); room-type
mapping. After this commit, everything left is app tier or explicitly
versioned-out — the §8.5.8 engine plan is DONE.
