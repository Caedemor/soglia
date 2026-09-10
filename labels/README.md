# labels/ — hand-labelled ground truth

Hand-labelled ground truth for the text-mail list (`data/text_mail_rooming_list_anonymized.txt`):
**47 named guests + 2 held** (the `+ 2 autisti` trailer), authored by reading the
source document rather than by running our parsers over it. That makes it the
**only independently authored ground truth in the repo to date** — every file in
`eval/expectations/` was bootstrapped from the pinned hand parse, so it cannot
catch an error the parser and the model share, while this one can. The harness
does **not** currently read it (`eval_harness.py` contains no reference to
`labels/`); wiring it in is the next eval task, deliberately not done in this
commit. `TEMPLATE_ground_truth.xlsx` is the blank labelling form for future
lists. See [docs/eval-audit-2026-09-10.md](../docs/eval-audit-2026-09-10.md) §4.

## Contents

- `text_mail_rooming_list_anonymized_ground_truth.json` — the machine-readable
  labels: 47 guest objects, a `held` entry (`+ 2 autisti`, `pax_expected: 2`),
  and `list_level` totals (47 named / 2 pending / 49 expected /
  `awaiting_completion`). Its `_meta` block records provenance and corrections.
- `text_mail_rooming_list_anonymized_ground_truth.xlsx` — the same labels in the
  spreadsheet the labelling was done in. Verified to match the JSON exactly.
- `TEMPLATE_ground_truth.xlsx` — blank form: the canonical `Guest` columns plus
  `guest_no`, `room_group`, `notes`, with dropdowns and per-field header
  comments.

## Known divergences — read before using this as eval ground truth

Both were checked against the anonymized source on 2026-09-10; every name traces
to that file and no real guest data is present. But two things will bite a naive
strict comparison:

1. **The `Ks.` honorific on guest 1.** The source line reads
   `Klimowicz` / `Ks. Tomasz`. The labeller recorded `nome: "Tomasz"` and
   expressed `Ks.` as a **role** instead (`tipo_alloggiato: "18"`, capo gruppo).
   The engine, by its *verbatim means verbatim* invariant, keeps `Ks. Tomasz` in
   the name field and assigns role `20`. Neither is wrong — they are different
   conventions — but a field-exact diff will flag this one guest. Decide which
   convention the eval scores against before wiring this in.
2. **The template is not empty.** `TEMPLATE_ground_truth.xlsx` carries one
   example row (KOVALCHUK IRYNA, DOB 23/02/1958, doc FZ180350, placeholder code
   100000999) marked `EXAMPLE ROW — replace`, kept as a format demonstration.
   That row is the golden-file fixture guest already committed in
   `build_golden.py`, `test_tracciato.py` and `test_validate.py` — anonymized
   sample data and placeholder codes, not a real guest. Delete the row when
   labelling a new list.
