"""
MIX18 end-to-end WITH the inference add-on, to show the payoff:
    python3 run_mix18_infer.py

  parse -> validate (wall of red) -> suggest -> accept -> validate (red collapses)
        -> format the now-complete guests into REAL Alloggiati bytes.

Accepting every suggestion here SIMULATES the human clicking "confirm" in review.
The point: the systemic reds become confirmable, and a real list formats to bytes
for the first time — with only the genuinely-incomplete guests left red.
"""
from collections import Counter

from parse_mix18 import parse
from validate import validate_guest, is_submittable
from infer import suggest, apply_suggestions
from tracciato import format_schedina

UA = "100000999"          # PLACEHOLDER Ukraine state code (verify vs real table)
ARRIVAL = "12/06/2026"    # the list's check-in; in production stamped at submission


def red_count(guests):
    c = Counter()
    for g in guests:
        for i in validate_guest(g):
            if i.tier == "red":
                c[i.field] += 1
    return c


def main():
    parsed = parse()
    before = [p.guest for p in parsed]
    n = len(before)

    # BEFORE inference
    rc_before = red_count(before)
    print(f"{n} guests parsed.  Red fields BEFORE inference:")
    for f, k in sorted(rc_before.items(), key=lambda kv: -kv[1]):
        print(f"    {f:<18} {k}")
    print(f"  submittable now: {sum(is_submittable(g) for g in before)}/{n}\n")

    # suggest, then accept-all (simulating the human confirming in review)
    total_suggestions = 0
    after = []
    for p in parsed:
        suggs = suggest(p.guest, list_country_code=UA, list_country_name="Ukraine")
        total_suggestions += len(suggs)
        after.append(apply_suggestions(p.guest, suggs))

    rc_after = red_count(after)
    print(f"Inference proposed {total_suggestions} values (advisory). After accepting them,")
    print("red fields AFTER inference:")
    if rc_after:
        for f, k in sorted(rc_after.items(), key=lambda kv: -kv[1]):
            print(f"    {f:<18} {k}")
    else:
        print("    (none)")
    submittable = [a for a in after if is_submittable(a)]
    print(f"  submittable now: {len(submittable)}/{n}\n")

    # who's left red, and why (the genuinely-incomplete — a human decision, not a gap we can guess)
    print("Still red (correctly — these need a human / the desk):")
    for p, a in zip(parsed, after):
        reds = {i.field for i in validate_guest(a) if i.tier == "red"}
        if reds:
            print(f"    {a.cognome} {a.nome:<10} ({p.role_note.split('[')[0].strip()}): {', '.join(sorted(reds))}")
    print()

    # the payoff: format the now-complete guests into real Alloggiati lines
    print(f"First real Alloggiati bytes from your actual list ({len(submittable)} formattable) \u2014 first 2 lines:")
    for a in submittable[:2]:
        line = format_schedina(a, data_arrivo=ARRIVAL, giorni_permanenza=2)
        print(f"    {a.cognome} {a.nome}:")
        print(f"    |{line}|  ({len(line)} chars)")


if __name__ == "__main__":
    main()
