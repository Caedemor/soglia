"""
Soglia — single entry point (what the web server / UI will call).

    python3 run.py

One call to the orchestrator returns one result object; everything below is just
reading that object. This is the pattern the real app uses — the demo scripts
(run_mix18.py, run_mix18_infer.py) collapse into this.
"""
from parse_mix18 import parse
from orchestrator import process_list

UA = "100000999"   # placeholder Ukraine code (verify vs real table)


def main():
    # The whole pipeline, in one line. Swap `parse` for the real LLM parser later;
    # nothing below changes.
    result = process_list(parse, infer_country_code=UA, infer_country_name="Ukraine")

    r = result.reconciliation()
    print(f"List processed: {r['total']} guests  |  "
          f"{r['submittable']} ready, {r['blocked']} need attention "
          f"(before anyone confirms suggestions in review).\n")

    print("Per-guest rollup (first 6):")
    for g in result.guests[:6]:
        reds = len(g.reds)
        sugg = len(g.suggestions)
        room = g.meta.get("room", "?")
        flag = "ready" if g.submittable else f"{reds} red"
        print(f"  {g.guest.cognome:<12} {g.guest.nome:<11} "
              f"room {room:<7} | {flag:<7} | {sugg} suggestion(s)")
    print()

    # one guest in full, so the result object's shape is visible
    leader = next(g for g in result.guests if not g.submittable)
    print(f"Detail \u2014 {leader.guest.cognome} {leader.guest.nome} "
          f"({leader.meta.get('role_note','').split('[')[0].strip()}):")
    for i in leader.reds:
        print(f"    RED  {i.field:<18} {i.message}")
    for s in leader.suggestions:
        print(f"    sugg {s.field:<18} -> {s.value}   ({s.basis})")
    print()

    n_bytes = len(result.tracciato(data_arrivo='12/06/2026', giorni_permanenza=2))
    print(f"tracciato() right now yields {n_bytes} bytes "
          f"({len(result.submittable)} submittable). After suggestions are confirmed in")
    print("review, the same call emits the full police file \u2014 see run_mix18_infer.py.")


if __name__ == "__main__":
    main()
