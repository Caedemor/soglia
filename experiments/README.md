# experiments/

Work that was built and evaluated but is **not part of the engine**. Nothing
here is imported by `run_tests.sh`, the pipeline, or the eval harness. Each
entry carries its status so a future session does not have to re-derive why it
is sitting here.

---

## `privacy_mask.py` — deterministic PII masker

**Status: preserved, not wired in. Re-run is the queued follow-up.**

**What it does.** The privacy architecture in one idea: real passport data
should never reach a cloud model. Stage 1 only needs to infer *which column is
which* — a question about structure, not content. So this module produces a
structure-preserving but PII-scrubbed copy of the sample rows; the returned
`ColumnMap` is then applied to the **real** rows locally in stage 2.

It is plain Python with **no model calls** — reliable by construction.
Alphabetic characters become random letters of the same case and script
(Latin→Latin, Cyrillic→Cyrillic); digits become random digits, except that a
date-shaped cell stays a valid calendar date in the identical written format;
a document-number cell keeps its exact letter/digit pattern. Header rows,
structural markers (`GUIDE` / `DRIVER` / `TOUR-LEADER` / `Ks.` / `Sig.` /
room+board codes), column order, empty cells, whitespace and casing are left
untouched. A seeded RNG makes it deterministic and reproducible.

**Validated PII-clean (June 2026).** A token-level check found **zero** real
name or date-of-birth tokens surviving across all three dev lists in use at
the time.

**Why it stalled.** Map quality held for polish (field-exact) and park
(structure intact), but **mix18 degraded** — and not in the predicted way. Name
*order* held fine. The real failure: with names scrubbed to gibberish, the
model lost the name as its guest-anchor and instead authored the skip rule
`column_empty col5` (the passport column), which **silently dropped the 3 real
passport-less guests** (39 → 36). An A/B confirmed it: unmasked produced the
safe skip 3/3, masked produced the harmful one 3/3. The 36 emitted guests were
otherwise a clean subset — the only damage was the drops.

**Why that blocker is now closed.** That failure class — a model-authored skip
rule silently deleting rows, bypassing validation because dropped rows are
never transcribed — was the exact class closed by the **non-destructive skip
fix** and, later, the **dispatch floor**. Skips are now review *hints*, not
deletes: a skip-matched row that still carries a name is emitted with
`skip_flag` set, which `validate_guest` turns into a RED. The contemporaneous
record notes this specific case explicitly — the mix18 harmful-skip scenario
now emits all 39 guests with the 3 passport-less ones flagged, data identical,
only the flag added. Nothing about this file changed; the ground underneath it
did.

**The queued follow-up.** A masked-vs-unmasked stage-1 comparison run through
`eval_harness.py` — the instrument that did not exist when the experiment was
first run. That is the honest way to find out whether the privacy architecture
is now viable end-to-end, and it is a live-API task, so it belongs on the
machine with the key.

**Caveat for whoever picks this up:** the masker was written against the dev
lists as they stood in June and has not been exercised since. Verify it still
runs against the current readers before drawing conclusions from any new
comparison.
