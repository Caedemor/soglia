# PLAN — STAY foundation (build commit 1 of addendum §8.5.8)

Branch: `stay-foundation`. Ground truth: addendum §8.5.2/§8.5.6/§8.5.7/§8.5.8;
handoff §8 + §13.1–13.4. Scope: STAY entity, identity/stay split, twin = one
STAY + two GUESTs, held capacity, reconciliation. OUT: PARTY (no party_id field
is added — a dead column would only exist to satisfy a later commit), submit-time
arrival stamping, cross-row room grouping, room-type-derived occupancy.

## 1. The one deviation from the approved constraints — pax_expected derivation

The constraint said a held row is "routed to a held STAY with pax_expected=N"
where N comes from the placeholder text. **The data disproves that reading.**
The Park list's 9 held rows restate the BLOCK total on every room row:
`Al.Mat. arrivi 18 pax` ×8 + `Al.Mat. arrivi 17 pax` ×1. Summing text-N gives
161 (or 35 if grouped by text) — both contradict §13.4's blessed arithmetic
(**41 expected / 23 named / 18 pending**). Each held row is one twin room
(the source's own TWIN=1 / PAX=2 columns confirm it).

**Decision:** a held row's `pax_expected` = the row's **name-slot capacity**
(`len(map.name_slots)`, park = 2). Deterministic, uses only what the frozen
ColumnMap already declares, and reproduces §13.4 exactly: 9 × 2 = 18. The
text-N is kept **verbatim on the Stay** (§8.5.7 — review context, never summed).
Room-type-column-derived occupancy is the named follow-up (it requires mapping
a column → ColumnMap contract change → stage-1 prompt + all three fixtures).
Consequence accepted: a held SINGLE row in a two-slot list would read as 2 —
none exist in the dev data; the follow-up fixes the general case.

## 2. Other design decisions

- **Held recognition** (`stay.held_pax`): `\b(\d{1,3})\s*pax\b`, case-insensitive,
  on the joined slot text. Catches "Al.Mat. arrivi 18 pax", "2 pax". Does NOT
  catch "Driver 1" (no pax), "PAXTON" (word boundary), "SGL"/"No. of rooms"
  (no count), or **"names pending" (no count — deliberately narrower than the
  constraint's example list: a held stay with unknowable pax must not feed
  arithmetic that could read as complete; count-less placeholders remain
  guard-red guests, which is the safe disposition).**
- **Row rule:** held only if EVERY filled slot matches. A mixed row (real name +
  placeholder slot) emits guests; the placeholder slot becomes a guard-red
  guest. Ambiguity goes to a human, never to arithmetic.
- **Precedence:** held recognition runs BEFORE the map-authored skip rule
  (deterministic code outranks model output). PARK_MAP keeps its skip rule —
  the frozen fixtures still carry it; it now matches zero rows.
- **One Stay per data row** that yields guests or is held; pax_expected for a
  named row = filled slots (a park twin = 2, complete by construction — the
  honest general case arrives with room-type mapping). Block aggregation of
  held rows is commit-3 territory (§8.5.3); per-row stays sum identically.
- **Unlinked guests** (bespoke `parse_mix18.py`, hand-built fixtures): count
  1-for-1 in reconciliation (expected += 1, named += 1) so legacy paths never
  read as pending. `Guest.stay_id = None` marks them.
- **Four dispositions** stay distinct: guest (named slots) / held-capacity
  (all-slots-placeholder-with-count → Stay, no guest) / skip-flagged (map rule,
  emit-and-flag — polish header/legend, 7) / guard-flagged (implausible name on
  an emitted guest — polish "Driver N", mixed rows, count-less placeholders).

## 3. Blast radius (file-by-file)

- `tracciato.py` — **TRIPWIRE deviation, flagged:** `Guest` lives here, so
  adding `Guest.stay_id: int = None` touches the file. The formatter and
  `build_golden.py` are byte-for-byte unchanged (golden suite proves it).
- `parser.py` — `transcribe_row` restructured around `_transcribe_row` (held
  check + Stay creation); new `TranscribeResult` + `transcribe_with_stays`;
  `transcribe` becomes a thin guests-only wrapper (park: 32 → 23).
  `TranscriptionReport` gains `held_stays`/`held_pax`.
- `stay.py` — NEW: `Stay`, `held_pax`, `reconcile` (§8.5.2), `completeness_status`.
- `maps.py` — adds `parse_park_stays()`; maps/fixtures otherwise untouched.
- `validate.py` — ZERO changes (guard is the backstop, unchanged).
- `llm_parser.py` + `llm_maps/*` — ZERO changes (contract frozen).
- `infer.py`, `parse_mix18.py`, `run.py`, `run_mix18*.py` — ZERO changes.
- `run_lists.py`, `run_llm.py` — ZERO changes (dynamic prints; park now 23).
- `orchestrator.py` — `ListResult.stays` + `completeness()`; `process_list`
  gains optional `stays=`. Existing `reconciliation()` dict untouched.
- `storage.py` — `stay` table; `guest.stay_id` column + `_GUEST_COLS`;
  `_STAY_COLS` + a second import-time drift assert for `Stay`; `init_db`
  migrates both new guest columns in place; `save_list(..., stays=None)`,
  new `load_stays`. The existing Guest drift assert fires until this lands —
  by design; Guest.stay_id and the storage change ship in the same commit.

## 4. Test plan + every changed assertion (old → new)

- `test_skip_nondestructive` — park (b): 32 guests/9 flagged, cognome
  startswith al.mat → **23 guests / 0 flagged / 9 held stays / Σ pax 18 /
  verbatim startswith Al.Mat / zero guests linked to held stays**. (c):
  `rep_park.guests == 32 and skip_flagged == 9` → **23 / 0 / held_stays 9 /
  held_pax 18**. Polish (7 flagged, drivers guard-only) and the synthetic
  mix18 column_empty case (39/3) unchanged — the skip floor is still proven.
- `test_name_plausibility` — `test_park_placeholders_flagged` (asserted 9
  al.mat GUESTS red) → **`test_park_placeholders_become_held`**: even with NO
  skip rule, 23 guests + 9 held stays leak zero placeholders into guests; PLUS
  a backstop case: a count-less "names pending" row IS emitted as a guest and
  guard-redded (non-submittable). Categorical test: park guests can no longer
  contain al.mat (asserted absent); drivers still the only guest-side
  placeholders. Heuristic units unchanged.
- `test_llm_parser` — PARK expected 32 → **23** (comment updated); parity
  `via_llm == via_hand` unchanged (same code path, identical stay_ids).
- `test_parser` — parity vs bespoke mix18 compares with `stay_id` normalized
  to None (bespoke predates stays; identity equality is the point). Twin
  synthetic gains: both twin guests share a stay_id, distinct from row 2's.
- `test_storage` — skip_flag round-trip fixture: park (no longer flagged) →
  **polish** (7 flagged). Park round-trip now saves+loads stays and asserts
  `stay_id` links survive; legacy-DB migration extended to cover `stay_id` +
  the stay table.
- `test_stay` — NEW suite: recognizer units (both directions), park end-to-end
  arithmetic (23/9/18 → 41/23/18 awaiting_completion), twins share a stay,
  mixed-row safety, reconcile/overage units, mix18 + polish pending 0,
  unlinked-guest fallback.
- `run_tests.sh` → 10 suites, ALL GREEN (10/10); CLAUDE.md ×3 and
  README_START_HERE ×2 count references updated in the same commit (the only
  doc lines touched; CLAUDE.md's file-map/state sections are deliberately left
  for the merge decision).

Invariants NOT weakened: golden byte-identity, no truncation, verbatim,
null-is-valid, non-held junk still emit-and-flag, zero real guests dropped.
