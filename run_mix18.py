"""
Run the MIX18 list end-to-end through the kernel and report honestly:
    python3 run_mix18.py

  parse (real .docx)  ->  canonical Guests  ->  validate (the gate)

This does NOT format to police bytes yet — and that's the honest finding: the
list is missing fields Alloggiati requires, so nothing is submittable until an
inference/check-in step fills them. The report shows exactly what's there, what
isn't, and the booking-vs-room structure.
"""
from collections import Counter, defaultdict

from parse_mix18 import parse
from validate import validate_guest

CANON_FIELDS = [
    "cognome", "nome", "sesso", "data_nascita", "comune_nascita",
    "provincia_nascita", "stato_nascita", "cittadinanza",
    "tipo_documento", "numero_documento", "luogo_rilascio",
]


def main():
    parsed = parse()
    guests = [p.guest for p in parsed]
    n = len(guests)
    nights = parsed[0].nights if parsed else 0
    print(f"Parsed {n} guests from the MIX18 docx.  Stay: {nights} nights.\n")

    # --- sample extracted records, so the extraction is visible -----------------
    print("Sample canonical records (extraction working on the real table):")
    for p in parsed[:4]:
        g = p.guest
        print(f"  row {p.row:>2}: {g.cognome:<12} {g.nome:<12} "
              f"DOB {g.data_nascita or '—':<10} doc {g.numero_documento or '—':<9} "
              f"room {p.room:<11} booking {p.order}")
    print()

    # --- field coverage: what the list gives vs what it doesn't -----------------
    print("FIELD COVERAGE (populated / total):")
    for f in CANON_FIELDS:
        filled = sum(1 for g in guests if getattr(g, f).strip())
        if filled == n:
            mark, note = "\u2713", "extracted"
        elif filled == 0:
            mark, note = "\u2717", "NOT in this list"
        else:
            mark, note = " ", f"{n - filled} blank"
        print(f"  {f:<18} {filled:>2}/{n}  {mark}  {note}")
    print()

    # --- the gate: what a human must resolve, grouped ---------------------------
    red_by_field = Counter()
    for g in guests:
        for issue in validate_guest(g):
            if issue.tier == "red":
                red_by_field[issue.field] += 1

    systemic = [f for f, cnt in red_by_field.items() if cnt == n]
    other = {f: cnt for f, cnt in red_by_field.items() if cnt < n}

    print("THE GATE \u2014 red issues across all guests:")
    print(f"  Systemic (every single guest, because the column isn't in the list):")
    for f in sorted(systemic):
        print(f"      {f}  \u2014  {n}/{n}")
    print(f"  Per-guest:")
    for f, cnt in sorted(other.items(), key=lambda kv: -kv[1]):
        print(f"      {f}  \u2014  {cnt}")
    print()

    # --- structure: rooms (stays) vs bookings (parties) -------------------------
    rooms = {p.room for p in parsed}
    bookings = {p.order for p in parsed if p.order.upper() not in ("TOUR-LEADER", "DRIVER")}
    room_to_orders = defaultdict(set)
    for p in parsed:
        room_to_orders[p.room].add(p.order)
    mixed = {r: o for r, o in room_to_orders.items()
             if len(o) > 1 and not (o & {"TOUR-LEADER", "DRIVER"})}

    print(f"STRUCTURE:  {len(rooms)} rooms (stays)  |  {len(bookings)} bookings (parties)")
    print("  Rooms shared by people from DIFFERENT bookings (roommates, not family):")
    for r in sorted(mixed):
        names = [p.raw_name for p in parsed if p.room == r]
        print(f"      {r:<11} {names[0]} + {names[1]}   (two separate bookings)")
    print("  -> room (stay) and booking (party) are different groupings: the §8 two-FK design.")
    print()

    print("NEXT: an inference slice turns the systemic reds (sesso, stato_nascita,")
    print("cittadinanza) into confirmable yellows; then real lists can format to bytes.")


if __name__ == "__main__":
    main()
