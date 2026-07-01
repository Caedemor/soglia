# §8.5 Lifecycle & export state — rev. 3 addendum A (July 1, 2026)

*Extends §8 rev. 3. Absorbs the incomplete-list / supplement / PMS-export decisions. Folds against §8.2 (`STAY`/held capacity §13.4, `SUBMISSION` §13.8, `origin = override` §13.7). Not yet merged into §8 — review first. Four build commits derive from this.*

The one-line thesis: **a list's "doneness" is two independent facts, not one — is everyone named (completeness), and what have we handed to the PMS (export coverage). They don't move together, so they're modelled as two orthogonal axes, never as a single status or a user-chosen "mode."**

---

## 8.5.1 Two orthogonal axes, not two workflows

The real-world prompt: a hotelier receives 30 booked, 25 named, 5 held (`names_pending`). One hotelier enters the 25 into the PMS now and waits for the 5; another waits until all 30 are named before touching the PMS. These look like two products. They are not. They are two trajectories through one 2-D state space:

- **Completeness** (Alloggiati-relevant): `awaiting_completion` → `complete` → `complete_by_override`. Computed from held capacity (§8.5.2). You cannot fully register a list with the police until everyone is named, because a held room has no person to put on a schedina.
- **Export coverage** (PMS/logistics, best-effort belief): `none` → `partial` → `full`. Computed from per-guest export records (§8.5.4).

The two "workflows" are just two paths: *wait* = hold export at `none` until completeness reaches `complete`; *export-as-you-go* = let export advance while completeness is still `awaiting_completion`. **No mode switch, no up-front setting, one code path.** The hotelier's clicks at each moment trace the path; the system never asks them to choose a lane.

Invariant: **the two axes are independent.** A list is routinely `awaiting_completion` (5 unnamed) *and* `partial` export (25 in the PMS) at the same time — that is the stepfather case, and it must be a first-class representable state, not an error.

---

## 8.5.2 Held capacity → reconciliation, made precise (refines §13.4)

§13.4 established held capacity as a `STAY` with `pax_expected` and `status = names_pending`. This pins the arithmetic, because "defer slot-binding to a counter" (§8.5.3) makes the per-`STAY` count the unit of truth.

Reconciliation is **per-`STAY`**, then summed:

- `pending_i  = max(0, pax_expected_i − named_guests_on_stay_i)`
- `overage_i  = max(0, named_guests_on_stay_i − pax_expected_i)`
- list `pending = Σ pending_i`; list `overage = Σ overage_i`

A normal named twin: `pax_expected = 2`, 2 guests → pending 0. A held block: `pax_expected = 18`, 0 guests → pending 18. After a supplement names all 18 onto that block: 18 guests vs 18 → pending 0, `status` flips `names_pending → complete`. If a supplement overfills a block (named > `pax_expected`), `STAY.status = over` — surfaced as the overage advisory (§8.5.3), never blocking completeness.

**Completeness = (`pending == 0`).** Overage does **not** block completeness — an extra named guest is still a registrable person — but it surfaces as an independent advisory (§8.5.3), because an overage is often a duplicate or a data error and a human should look. The "row ≠ guest" safeguard from §13.4 stands: counting is PAX-aware (a twin contributes 2 to `pax_expected`), never a raw row count, and a held room can never silently read as complete.

---

## 8.5.3 Supplement flow — list-level match, slot-binding deferred (refines §13.4)

When the named people behind a held block arrive as a later file:

**List-level attachment is a UI selection, not an inference.** The hotelier sees their open lists (anything not `complete`), picks the one this supplement belongs to, and hits "add more guests." Soglia does not guess which *list* — the human says. This is the `relation_to_prior = supplement` path (§13.4): a new `LIST_VERSION` carries prior guests forward and adds the newly-named ones.

**Slot-level binding is deferred to a counter (v1 decision).** Soglia does **not** resolve which specific room inside a held block each new name fills. The held block is one coarse `STAY` (e.g. "the 18-pax Al.Mat block"); supplement names attach to that one `STAY` as a group, decrementing its `pending` until the block is full. A `GUEST` still has exactly one `STAY` (§8.1) — the block stay — just not a room-resolved one. Consequence accepted on purpose: the PMS export for supplement guests carries the block, not a specific room number, which is fine for hotels that assign rooms in the PMS anyway. Revisit only if a hotelier needs room-accurate supplement export; the machinery to upgrade is the same fuzzy-confirm pattern as `person_key` (§13.9), deliberately not built twice before v1 ships.

**Reconciliation expects mismatch, never assumes equality.** `pax_expected` and the actual supplement count routinely disagree:
- supplement short (got 17 of 18): `pending = 1` → "expected one more on this block."
- supplement over (got 19 of 18): `overage = 1` → "one extra — check for a duplicate or an added guest."
Both are surfaced; neither crashes the count. Re-running §8.5.2 after each supplement is the whole mechanism.

---

## 8.5.4 PMS export reuses `SUBMISSION`, honestly (refines §13.8)

A PMS export is a `SUBMISSION` with `target = pms`. This buys per-guest export tracking for free and keeps "what hand-offs has this guest been part of" in one place. But a PMS export is **not** a verified submission, and the model must not let it masquerade as one.

- **`SUBMISSION.target`** ∈ `{ alloggiati, pms }`.
- **Status lifecycle for `target = pms`:** `generated` (file exists, `artifact_hash` set) → `export_confirmed` (the human clicked the confirm popup, §8.5.5). These are two states on purpose: a downloaded-but-unconfirmed export is a visible limbo Soglia can nudge on ("you generated this 20 min ago — did it import?"), not a void. Only `export_confirmed` flips guests to exported. (Police keep the §13.8 lifecycle: `pending | accepted | partial | rejected`.)
- **`SUBMISSION_RESULT.outcome` for PMS = `exported_unverified`**, written per included guest at `export_confirmed`. Never `accepted` — nothing accepted it. The Alloggiati portal returns a real per-guest verdict (`accepted`/`rejected` + `portal_reason`); the PMS returns nothing, so a PMS result records *intent the human confirmed*, not *outcome a system reported*. This keeps "best-effort belief" honest **inside the data model**, not just in the UI copy.

**Export coverage (§8.5.1) is computed from this:** a named guest is "exported" iff they have a `SUBMISSION_RESULT(target = pms, outcome = exported_unverified)` from an `export_confirmed` submission. Coverage rollup: `none` / `partial` / `full` over named guests.

**Delta export, surfaced first; re-export always available, non-destructive.** Because Soglia cannot see the PMS, the human is the only source of truth, so:
- A new PMS export defaults its guest set to **un-exported named guests** (the delta) — this is the no-duplicates default that handles the stepfather case (25 already in → next export offers only the 5).
- "Export everything (30)" is always offered, but the delta is shown **first** so the default path can't silently re-push the 25 as duplicates.
- Re-export never deletes prior export records; it appends a new `SUBMISSION` and marks the prior PMS export `status = superseded` (a later export re-exported over it) — the superseded record stays as history, never deleted. History is the audit trail. `idempotency_key` (§13.8) still guards against a double-click writing the same hand-off twice.

---

## 8.5.5 "Mark complete" and "confirm export" are audited human assertions (extends §13.7)

Both actions are the §13.7 `origin = override` philosophy — "machine flagged X, human took responsibility on this date" — applied above field level. They are recorded assertions, not boolean flips:

- **Mark-complete-despite-pending.** A hotelier whose last 3 guests went into the PMS by hand can assert the list complete while `pending > 0` → completeness becomes `complete_by_override`, recording `{ actor, timestamp, pending_at_override, reason }`. Red-gated: the action sits behind an explicit "this list is INCOMPLETE — N guests are still unnamed. Mark complete anyway?" confirmation. The record — not the warning — is the point; it's the defensible "human vouched for the gap" artifact the product sells.
- **Confirm-export.** The `generated → export_confirmed` transition (§8.5.4) is the same shape: the human asserts "the file imported correctly," recorded with `{ actor, timestamp, guest_count }`. It is a belief that can be wrong, and that is the honest ceiling without a PMS API — so we *log whose belief it was and when*, rather than pretending it's verified.

Both records live at the level of the thing asserted: completeness-override on `LIST_VERSION`, export-confirm on `SUBMISSION`. Same lineage as §13.7, different altitude.

---

## 8.5.6 Entity deltas (what the build commits add)

- **`LIST_VERSION`**: `completeness_status` (`awaiting_completion | complete | complete_by_override`, computed except for override) — this **renames the draft's `alloggiati_coverage`** (§8.2), it is not an additional field; `completeness_override` json nullable `{ actor, ts, pending_at_override, reason }`; `export_coverage` (`none | partial | full`, computed); `reconciliation` json computed `{ expected, named, pending, overage }` — this **replaces the draft's `coverage_detail`**. One field per axis (completeness, export); the draft's `alloggiati_coverage`/`coverage_detail` pair is superseded, never carried alongside these.
- **`STAY`**: already has `pax_expected`, `status`. `status` enum gains/keeps `names_pending | complete | over`. No new room-resolution fields in v1 (slot-binding deferred).
- **`SUBMISSION`**: `target` (`alloggiati | pms`); `status` widened so `pms` uses `generated | export_confirmed | superseded`; `export_confirm` json nullable `{ actor, ts, guest_count }`.
- **`SUBMISSION_RESULT`**: `outcome` gains `exported_unverified` for `target = pms`.
- **`GUEST`**: unchanged. (Export state is read off `SUBMISSION_RESULT`, not stamped on the guest — one source of truth.)

---

## 8.5.7 The two-lens consequence, stated once

Held capacity behaves oppositely on the two adapters, and both must be honoured:

- **Alloggiati (police):** a held room produces **no schedina** — nobody to register — so it is never submitted now. Its only job on this lens is to keep completeness at `awaiting_completion` so the hotel cannot submit thinking they're done. The names arrive later (supplement) and *then* become schedine.
- **PMS (logistics):** a held room **is** a real reservation (room/board/dates/`pax_expected`) and flows to the PMS export as a booking, per the hotelier's chosen path. "Drop and forget" fails both lenses at once — it loses a PMS reservation *and* erases the "list incomplete" signal, the second being the more dangerous because it's a false all-clear on a police filing.

---

## 8.5.8 v1 builds vs stubs

**This section supersedes draft §8.4's stub list for the incomplete-list / export scope:** supplement accumulation (`relation_to_prior = supplement`, §8.5.3) and PMS-target `SUBMISSION_RESULT` (`exported_unverified`, §8.5.4), which §8.4 deferred, are **build-now** here. §8.4's other defers stand unchanged — the Alloggiati partial/reject `SUBMISSION_RESULT` path and `person_key` cross-version diff remain stubbed.

- **Build now:** the two-axis state (§8.5.1); held-capacity reconciliation with mismatch (§8.5.2); supplement as `relation_to_prior = supplement` with list-level UI selection and counter-based decrement (§8.5.3); PMS export as `SUBMISSION(target = pms)` with `generated → export_confirmed`, `exported_unverified` results, delta-first non-destructive re-export (§8.5.4); both audited assertions with red gates (§8.5.5).
- **Stub / defer:** slot-level supplement binding (room-resolution inside a held block) — deferred to the per-`STAY` counter, revisit on real hotelier need; live PMS API confirmation (we will never have a verified outcome without it, by design); `person_key` cross-version diff stays as in §8.4.
- **Build order (four commits, each independently testable):** (1) `STAY` foundation — identity/stay split, twin = one `STAY` + two `GUEST`s, held capacity + reconciliation; (2) export-state tracking + delta export; (3) supplement accumulation + mismatch-tolerant reconciliation; (4) override + audit (mark-complete, export-confirm) with red gates. The name-plausibility guard and the non-destructive skip change remain the safety floor underneath all four; held-capacity classification is primary, the guard is the backstop.
