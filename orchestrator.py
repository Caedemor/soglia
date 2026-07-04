"""
Soglia — the orchestrator (the top of the pyramid).

This composes the pieces we built into ONE pipeline with ONE result. It adds no
new logic; it just runs the steps in order and packages the outcome so a caller
(the web server, a CLI, a test) reads a single object instead of re-wiring the
steps each time.

Pipeline:
    source document --[parser]--> canonical Guests
                                      |
                                      +--> validate each (the gate)
                                      +--> [optional] inference suggestions
                                      +--> reconcile (counts)
                                      +--> completeness (stays, §8.5.2)
                                      +--> format the submittable ones -> bytes

The parser is a SWAPPABLE INPUT, not hardwired. Today we pass in the MIX18
parser; when the real LLM parser exists it slots into this same seam and nothing
else changes. That is the whole point of having an orchestrator.
"""
from dataclasses import dataclass, field

from validate import validate_guest, Issue
from stay import reconcile, completeness_status
from infer import suggest, Suggestion
from tracciato import Guest, format_schedina, format_tracciato


@dataclass
class GuestResult:
    """Everything known about one guest after the pipeline runs."""
    index: int
    guest: Guest
    issues: list            # list[Issue]  — the gate's findings
    suggestions: list       # list[Suggestion] — advisory, may be empty
    meta: dict = field(default_factory=dict)   # parser context: room, booking, etc.

    @property
    def reds(self):
        return [i for i in self.issues if i.tier == "red"]

    @property
    def submittable(self):
        return len(self.reds) == 0


@dataclass
class ListResult:
    """The single object the pipeline hands back for a whole list."""
    guests: list            # list[GuestResult]
    stays: list = field(default_factory=list)   # list[Stay] — named/held/unrecognized (+ over via supplements)

    @property
    def total(self):
        return len(self.guests)

    @property
    def submittable(self):
        return [g for g in self.guests if g.submittable]

    @property
    def blocked(self):
        return [g for g in self.guests if not g.submittable]

    def reconciliation(self) -> dict:
        return {
            "total": self.total,
            "submittable": len(self.submittable),
            "blocked": len(self.blocked),
        }

    def completeness(self) -> dict:
        """§8.5.2 + §8.5.1: PAX-aware reconciliation and the completeness axis.
        {expected, named, pending, overage, unrecognized, status}. Guests without a stay link
        (legacy parsers) count 1-for-1; a held room keeps status at
        awaiting_completion until its people are named. Orthogonal to
        reconciliation() (submittability), per the addendum's two axes."""
        rec = reconcile(self.stays, [g.guest for g in self.guests])
        rec["status"] = completeness_status(rec)
        return rec

    def tracciato(self, *, data_arrivo: str, giorni_permanenza: int) -> str:
        """The police file for the submittable guests (bytes the portal accepts)."""
        ready = [g.guest for g in self.submittable]
        return format_tracciato(ready, data_arrivo=data_arrivo,
                                giorni_permanenza=giorni_permanenza)


def process_list(parser, *, stays=None, infer_country_code: str = None,
                 infer_country_name: str = None) -> ListResult:
    """
    Run the pipeline.

    `parser` is any zero-argument callable returning a list of objects that each
    expose `.guest` (a canonical Guest) and, optionally, `.row` / `.room` /
    `.order` / `.role_note` for context. The MIX18 parser satisfies this; so will
    the real one. Pass infer_* to attach advisory suggestions (optional), and
    stays= (from transcribe_with_stays) to enable completeness() reconciliation.
    """
    parsed = parser()
    results = []
    for i, p in enumerate(parsed):
        g = getattr(p, "guest", p)            # tolerate a bare Guest too
        meta = {k: getattr(p, k) for k in ("row", "room", "order", "role_note")
                if hasattr(p, k)}
        suggestions = (suggest(g, list_country_code=infer_country_code,
                               list_country_name=infer_country_name)
                       if infer_country_code else [])
        results.append(GuestResult(index=i, guest=g,
                                    issues=validate_guest(g),
                                    suggestions=suggestions, meta=meta))
    return ListResult(guests=results, stays=stays or [])
