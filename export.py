"""
Soglia — PMS export artifact + submission entities (addendum §8.5.4).

A PMS export is a SUBMISSION with target=pms: lifecycle generated ->
export_confirmed (-> superseded when a later export lands over it). Only a
CONFIRMED export flips guests to exported; the PMS reports nothing back, so a
result records intent the human confirmed (`exported_unverified`), never
`accepted` (§8.5.4 — "best-effort belief" kept honest inside the data model).

The artifact builder here is PURE and INJECTABLE: storage.record_pms_export
takes the artifact TEXT as an argument, so a PMS-specific template (the real
Bedzzle import sheet is requested from the field — PLAN-export-state.md §6)
lands later as another builder function with ZERO machinery change. The
canonical CSV is v1's artifact and remains the internal representation either
way (§13.5: "the canonical list is the product; every PMS output is a cheap
row-operation off it").

Lens rule (§8.5.7): held stays ARE bookings and ride into the artifact
(names_pending, pax_expected, verbatim); `unrecognized` stays do NOT — they
are attention items that gate completeness, not hand-off content.
"""
import csv
import io
from dataclasses import dataclass


@dataclass
class Submission:
    """One recorded hand-off of a list version to a target system.

    `id` mirrors the storage PK (results reference it; confirm_export takes
    it) — unlike Guest/Stay, a submission's identity IS its storage row."""
    list_version_id: int
    target: str                   # "alloggiati" | "pms"
    idempotency_key: str          # §13.9: a double-click never records twice
    status: str                   # pms: generated | export_confirmed | superseded
                                  # alloggiati: pending (verdict loop stubbed, §8.5.8)
    submitted_arrival_date: str   # §13.2: stamped at submission time ("" for pms)
    artifact_hash: str            # sha256 of the exact bytes handed over
    submitted_at: str             # ISO timestamp
    export_confirm: str = ""      # §8.5.5 audit json {actor, ts, guest_count} — commit 4 fills
    id: int = None                # storage PK (None until persisted)


@dataclass
class SubmissionResult:
    """Per-guest line of a submission. For pms: created as a MANIFEST row
    (outcome="") at generation — the confirm must confirm exactly the
    generated file's guest set — and upgraded to `exported_unverified` at
    export_confirmed (plan call 3). Coverage queries the outcome, so
    manifests never count. portal_* fields belong to the stubbed Alloggiati
    verdict loop and stay empty in v1."""
    submission_id: int
    guest_id: int                 # storage guest.id — within-version identity (plan call 7)
    outcome: str                  # "" (manifest) | "exported_unverified"
    portal_line_no: int = None
    portal_reason: str = ""


# Fixed, deterministic column order — stable bytes => stable artifact_hash.
PMS_CSV_COLUMNS = ["row_type", "stay_id", "cognome", "nome", "sesso",
                   "data_nascita", "cittadinanza", "tipo_documento",
                   "numero_documento", "pax_expected", "note"]


def build_pms_csv(guests, stays) -> str:
    """The canonical PMS artifact: named guests in list order, then held
    stays (bookings awaiting names) by stay_id. Deterministic bytes: fixed
    columns, "\\n" line endings, csv-module quoting. Missing identity fields
    export as empty cells — a named guest with gaps is still a real booking
    on the logistics lens (plan call 5); reds gate the ACTION (commit 4),
    never the content. `unrecognized` stays are excluded (§8.5.7 lens rule)."""
    pax_by_stay = {}
    for s in stays:
        pax_by_stay[s.stay_id] = s.pax_expected

    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(PMS_CSV_COLUMNS)
    for g in guests:
        w.writerow(["guest", g.stay_id if g.stay_id is not None else "",
                    g.cognome, g.nome, g.sesso, g.data_nascita,
                    g.cittadinanza, g.tipo_documento, g.numero_documento,
                    pax_by_stay.get(g.stay_id, 1), ""])
    for s in sorted((s for s in stays if s.status == "names_pending"),
                    key=lambda s: s.stay_id):
        w.writerow(["held_names_pending", s.stay_id, "", "", "", "", "", "",
                    "", s.pax_expected, s.verbatim])
    return out.getvalue()
