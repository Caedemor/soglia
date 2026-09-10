# Eval-instrument audit — 2026-09-10

**What this is:** the findings of an audit of the stage-1 eval instrument
(`eval_harness.py` / `run_eval.py`, suite 15) and of scorecard #1
(`eval/scorecards/2026-07-08-inaugural.json`). The audit was conducted
report-only — no code was changed — and until now its findings lived only in a
conversation transcript. This file makes them part of the record.

`docs/handoff-rev5.md` is sealed and is NOT modified by this document. Nothing
here contradicts rev5; it qualifies what a scorecard PASS means.

**Provenance key** — every claim below is tagged, because the value of this
file is that a future reader can tell established fact from inference:

- **[MEM]** — from the project memory recorded at the time (2026-07-08),
  restored to `~/.claude/projects/-Users-wardo-Projects-Soglia/memory/` on
  2026-09-10 after the repo move stranded it.
- **[CODE]** — re-verified against the working tree at `070155b` on
  2026-09-10, by reading the file or running the check named.
- **[AUDIT]** — a conclusion drawn in the 2026-09-10 audit session. It rests
  on the [CODE] items cited with it; it is reasoning, not a new measurement.

---

## 1. What scorecard #1's PASS establishes — and what it does not

**[MEM]** Scorecard #1 (2026-07-08, `claude-sonnet-4-6`, 2 runs per list, 8
live calls) returned verdict **PASS** on all four dev lists with every hard
gate green. The one genuine run-to-run variance was textmail's
`doc_type_passport` mapping — present in run 1, absent in run 2.

**[AUDIT]** That PASS is evidence of **no-regression, not of accuracy.** It
establishes that the live model reproduces our own frozen reading of four
documents at the level of person names and held-pax totals, and that the full
engine path runs green on the model's output. It does not establish that
extraction is correct, because no gate inspects the field values that actually
fill a schedina. See §3.

**[AUDIT]** One honest qualifier, which does not change that classification:
the *person names and counts* — though not the field-coverage numbers — did
receive corroboration outside the instrument. During the 2026-09-10 audit
session, all four lists' person counts were re-derived directly from the source
documents (39 / 48 / 23 / 47), and polish's 48 persons were key-matched against
the document's own numbered rows. That corroboration exists in the record and
is re-runnable, but the instrument neither produced nor consumes it.

## 2. Ground-truth provenance: the expectations files

**[CODE]** All four files in `eval/expectations/` carry the same `notes` field:

> "bootstrapped from the pinned hand parse (PLAN-eval-harness §7); future
> lists: hand-authored from the document itself."

**[AUDIT]** So for the current corpus the reference was generated from our own
parsers' output and then frozen. Hand-authoring from the document is the stated
standard for *future* lists; it is not how these four were produced. An
expectations file derived from the parser cannot, by construction, catch an
error the parser and the model share.

**[CODE]** The hand-written maps in `maps.py` do enter the harness separately,
as the fourth corpus tuple element (`hand_names` in `run_eval.py`), but only
to compute the **soft** `handmap_parity` metric — it can never fail a list.

## 3. What the gates actually assert

**[CODE]** The five hard gates and their pass conditions:

| gate | passes when | can pass while extraction is wrong? |
|---|---|---|
| `map_valid` | the model's JSON compiles to a `ColumnMap` | yes — wrong-but-well-formed maps compile |
| `recall` | every expected person's *name* is found (casefolded token multiset over cognome+nome) | yes — names only |
| `held_arithmetic` | Σ `pax_expected` of held stays equals the expected total | largely — it checks the sum, not which rows |
| `required_fields` | promoted fields reach full coverage | **vacuous today** — see below |
| `engine_path` | persist → completeness → artifact → export → confirm → coverage `full` | yes — it proves the machinery runs |

**[CODE]** `required_fields` is `[]` in all four expectations files (mix18,
polish, park, textmail). The dial exists and works; it is currently switched
off everywhere, so this gate asserts nothing on any list.

**[AUDIT]** Consequence, stated plainly: **no gate asserts anything about
dates, document numbers, sex, or any other field value.** Field coverage is
reported as a soft metric only. A map that read mix18's Check-In column as
`data_nascita` would produce plausible-looking dates, shift a soft coverage
number, and pass every hard gate.

**[AUDIT]** `recall`'s name-multiset matching is also order-insensitive by
design, so a surname/given-name swap is invisible to it. That was a deliberate
design call (robustness to slot-order flips), not an oversight — but it is part
of what a PASS does not cover.

## 4. `labels/` — the one independently authored ground truth

**[CODE]** `labels/` holds hand-labelled ground truth for the text-mail list
(47 named guests + 2 held), authored from the source document, plus the blank
labelling template.

**[CODE]** `grep -rn "labels" eval_harness.py run_eval.py test_eval_harness.py`
returns nothing: the harness does not read it.

**[AUDIT]** So the only reference in the repo that was *not* derived from our
own parsers is not consumed by the instrument whose expectations it could
independently check. Wiring it in is the natural first eval-hygiene task; it is
deliberately not done in this housekeeping pass.

## 5. The holdout fence

**[CODE]** `guard_path()` in `eval_harness.py` refuses a path only when
`"real-data"` appears as a path segment. The tracked directory
`holdout test data/` (three anonymized lists) is **not** matched by it — a
`guard_path("holdout test data/…")` call is accepted.

**[MEM]** The standing rule (`holdout-is-test-only`) is emphatic: those three
lists are a held-out evaluation set, never to be used for development, stage-1
runs, or prompt tuning, because touching them destroys the honest read on
generalization that the ~20-list eval task depends on.

**[AUDIT]** The seal has held in practice — the 2026-09-10 audit found no
commit touching those paths since the original add, no live capture naming a
holdout list, and no scorecard covering one. But it is currently protected by
convention and discipline, not by code. Extending `guard_path` to cover
`holdout test data/` alongside `real-data/` is a cheap, obvious hardening.

## 6. Queued non-blocking fixups

**[MEM]** Three findings were raised at the eval-harness review on 2026-07-08
and explicitly classed non-blocking, which is why the branch was merged:

1. **Crash-guard breadth.** `evaluate_run` guards only `parse_map_json`. A map
   that *compiles* but carries wrong-typed values (string or float column
   index, string `header_rows`) crashes during transcription instead of
   producing a verdict — so one such model answer kills a whole campaign
   mid-run. Scoped fix: broaden the guard around transcription. Deeper fix:
   type-validate columns in `parse_map_json` — but that is a frozen engine
   surface, so it belongs to its own cycle.
2. **No retry on transient HTTP.** The first inaugural live attempt died on an
   API 529 mid-campaign and had to be restarted from scratch. A retry wrapper
   is cheap and matters before any ~20-list campaign.
3. **Stability metric diluted by prose.** The metric hashes the whole soft-metric
   dict including `review_notes`, which is free model prose, so it reports
   "unstable" almost always. With `review_notes` excluded, 3 of the 4 lists were
   perfectly stable and textmail's `doc_type_passport` flip stood out as the one
   real instability — which is exactly the signal the metric exists to surface.

## 7. What this audit does not change

The engine itself is not implicated. `run_tests.sh` is green (15/15) and the
hard invariants hold. The instrument's *machinery* is sound — gates, matcher,
rails, deterministic scorecards, and the `--live` opt-in all behave as
designed, and the `real-data/` refusal works. What the audit qualifies is the
**epistemic weight of a PASS**: treat scorecard #1 as a drift alarm, and do not
cite it as an accuracy measurement, until the field-level gates are switched on
and at least one reference is authored independently of our parsers.
