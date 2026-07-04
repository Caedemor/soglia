# PLAN — supplement accumulation + mismatch-tolerant reconciliation (commit 3)

Branch: `supplements` off main `f1bd457`. Ground truth read verbatim before
design: addendum §8.5.1–§8.5.3 (the supplement flow), §8.5.6 (entity deltas),
§8.5.7 (two-lens rule); handoff §13.4 (`relation_to_prior`), the §8.1 mermaid
(LIST_VERSION / GUEST shapes), §8.4 (build/stub line). STATUS: design brief —
awaiting approval, no implementation yet.

## 1. What the doc settled (no forks)

- A supplement is a **new `LIST_VERSION`** with `relation_to_prior =
  supplement`: prior guests carried forward, newly-named guests added
  (§8.5.3, §13.4). Versions stay immutable snapshots.
- **List-level attachment is a UI selection, not an inference** — the caller
  says which list/version the supplement belongs to. The engine never
  guesses.
- **Slot-binding is deferred to a counter.** The held capacity is ONE coarse
  block `STAY` ("the 18-pax Al.Mat block"); supplement names attach to it as
  a group; `pending` decrements per §8.5.2. No room resolution in v1.
- **Mismatch is expected, never fatal**: short supplement → `pending` stays
  positive; overfull → `overage` advisory and `STAY.status = over` — which
  becomes REACHABLE for the first time this commit. Overage never blocks
  completeness (an extra named person is still registrable).
- **`GUEST` is unchanged** (§8.5.6) — nothing gets stamped on the guest.
- §8.5.7 both-lens rule: the block stay keeps flowing to the PMS artifact as
  a booking (commit 2's CSV already does this) and keeps completeness at
  `awaiting_completion` until filled.

## 2. The design calls (each vetoable)

1. **Export lineage — the forced move, and why it is NOT person_key.**
   §8.5.3 makes a supplement a NEW version; §8.5.4's stepfather requires the
   carried 25 to STAY exported ("next export offers only the 5"). Commit 2's
   delta is per-version over `guest.id`, so the two sections jointly force
   export facts to survive carry-forward. Mechanism: a `guest_lineage`
   table (`guest_id → prior_guest_id`), written ONLY by the supplement
   carry-forward — a deterministic copy WE perform, exact by construction.
   The stubbed `person_key` (§8.4, §13.9) is fuzzy matching of independently
   re-uploaded documents; this is neither fuzzy nor a match — it is
   provenance of our own copy. Coverage and the delta become ancestor-aware
   (a guest is exported iff it or any lineage ancestor has a confirmed
   result). A separate table keeps the Guest dataclass pure, honors
   §8.5.6's "GUEST: unchanged," and leaves the storage drift mirror intact.
2. **Block aggregation at supplement time, not parse time.** Parsing is
   untouched (park still yields its 9 per-row held stays — commit 1
   behavior, all pins stand). When a supplement is APPLIED, the new
   version's held pool is merged into ONE coarse block stay: `pax_expected =
   Σ` prior held pax (park: 18, matching §8.5.3's own example verbatim),
   `verbatim` = the distinct prior held texts joined (§8.5.7 provenance
   preserved), `source_row = None` (it spans rows). Named/complete and
   `unrecognized` stays carry forward unchanged. The prior version is never
   touched.
3. **Supplement guests attach to the block** (`stay_id` = the block's), and
   the block's status is recomputed by counter after application:
   `names_pending | complete | over`. A supplement document's OWN non-guest
   rows (held or unrecognized rows found while parsing the supplement file)
   carry into the new version untouched — the dispatch floor survives
   supplements: junk in a supplement can no more vanish than junk in a
   roster. A supplement's own held rows ADD capacity (they are new held
   bookings), they do not merge into the prior block.
4. **`relation_to_prior` lands as a real column** (ALTER migration, the
   skip_flag pattern; existing rows read `''`). `save_list` marks new
   versions `initial`; `apply_supplement` marks `supplement`. `version_no`
   and the `SOURCE_DOCUMENT` entity stay deferred (app-tier; recorded in
   rev5). The plain re-upload/correction path is untouched this commit and
   keeps its known ceiling (fresh export history — the person_key stub).
5. **API shape**: `apply_supplement(conn, prior_version_id, supplement,
   *, source_filename) -> new_version_id` in storage.py (SQL stays in one
   file), where `supplement` is a `TranscribeResult` — the supplement file
   goes through the same stage-1/stage-2 pipeline as any list. A tiny pure
   helper `derive_status(pax_expected, named)` lands in stay.py.
6. **The status write.** Stay.status is stored data; after application the
   block's stored status reflects the counter. Reconciliation (§8.5.2)
   remains the computed truth; the stored status is kept consistent at the
   only moment it can change (application). No other stay's status is ever
   rewritten.

## 3. Cycle structure — including the holistic doc update (user request)

- **Commit 0 (warm-up, proposed):** the two queued mechanical bugs, finally.
  (a) `norm_dotted_date` 2-digit years: STOP inventing a century. Proposed
  fix: leave the value verbatim (unnormalized) so the validator reds the
  format and a human decides — "never invent" over convenience. The
  alternative (a 19xx/20xx pivot rule) is standard but IS inference;
  flagged for veto. (b) `_mix18_role` guards `row[7]` (short row → default
  role, not a crash). Both with tests, separately green.
- **Plan commit:** this file.
- **Implementation commit(s):** §2 above + `test_supplements.py` (suite 13).
- **Closing commit — the doc update, timed to be true at merge:**
  `docs/handoff-rev5.md`, a NEW record (rev4 stays frozen history): as-built
  architecture through commit 3, stage-1 status corrected (run LIVE,
  fixtures are captured model output with review_notes, ~cents/list cost),
  the reading order (rev5 → addendum-A → draft rev3 → rev4), and the §7.4
  decision RECORDED: the code's rolling 120-year cap is canonical; the
  draft's fixed "1920–2026" was an era-bound approximation. Plus the full
  living-surface sweep (CLAUDE.md current-state rewrite, READMEs, 13/13
  counts). /docs records other than the new rev5 remain untouched.

## 3b. Build-time addendum (discovered designing the chain test)

Carried guests whose `stay_id` points at a MERGED held stay (i.e. names a
previous supplement already attached to the previous block) are re-pointed to
the new block during carry-forward. Without this, a chain of supplements
orphans them — their stay vanishes in the merge and `pending` silently
corrupts. Pinned by the chain-of-two test.

## 4. Test plan (test_supplements.py) + touched assertions

**The flagship — the whole Monday→Wednesday story on real data:** textmail
parse (47 named + held trailer pax 2) → export 47, confirm → coverage
`full`, completeness `awaiting_completion` (commit 2's flagship state) →
**apply supplement naming the 2 drivers** → new version: 49 guests, block
`complete`, completeness **`complete`**, coverage `partial` (the 2 are new)
→ delta offers EXACTLY the 2 (the 47 stay exported through lineage) →
export + confirm → coverage `full`. Both axes traverse end-to-end through a
supplement; every intermediate state asserted.

Also: the stepfather numbers as a pin (25 exported + 5 supplement → delta
5); short supplement (pending stays positive, still awaiting); overfull
supplement (`over` reachable, overage advisory, completeness still
`complete` — §8.5.2 pinned); floor-through-supplement (a supplement
containing an unrecognized row blocks the new version's completeness);
chain of two supplements (lineage depth 2 — delta still right); prior
version byte-untouched after application; `relation_to_prior` round-trips;
legacy migration (ALTER + new table on an old DB). Existing suites:
byte-stable, ZERO assertion changes — parsing behavior is untouched.

## 5. Out of scope (named)

Override + audit + red gates (commit 4, incl. the regeneration-corner UX
note); person_key / correction diffing; room-resolved supplement binding
(§8.5.3 defers explicitly); SOURCE_DOCUMENT entity; any UI.
