"""Assignment-intent reading and patient-match resolution (suggestions / fuzzy auto-apply)."""
import uuid
from typing import Any

from sqlalchemy.orm import Session as DbSession

# ``match_patient_from_patient_information`` is resolved through the package namespace (not a direct
# import) so tests can monkeypatch ``app.services.ai_jobs.match_patient_from_patient_information`` and
# have ``suggested_reassignment_candidate`` honor it — preserving the pre-split behavior where this
# module's globals WAS the package namespace.
import app.services.ai_jobs as ai_jobs_pkg
from app.models import Session
from app.services.patient_matching import NATIONAL_ID_CONFLICT_RISK

__all__ = [
    "assignment_intent_basis",
    "out_of_context_marker",
    "caption_review_marker",
    "CAPTION_LOW_CONFIDENCE_THRESHOLD",
    "should_apply_identity_assignment",
    "spoken_name_from_information",
    "suggested_reassignment_candidate",
    "near_match_suggestion",
    "fuzzy_auto_apply_candidate",
    "NEAR_MATCH_SUGGEST_THRESHOLD",
    "MATCH_STRICTNESS_AUTOAPPLY_THRESHOLD",
]


def assignment_intent_basis(output: dict[str, Any]) -> str | None:
    """Return the assignment-intent basis ('explicit'/'implicit') from AI output, if present."""
    intents = output.get("intents")
    if not isinstance(intents, dict):
        return None
    assignment = intents.get("assignment")
    if not isinstance(assignment, dict) or assignment.get("present") is not True:
        return None
    basis = assignment.get("basis")
    return basis if basis in {"explicit", "implicit"} else "implicit"


def out_of_context_marker(output: dict[str, Any]) -> dict[str, Any] | None:
    """Return a staff-overridable out-of-context marker from AI intents, if flagged."""
    intents = output.get("intents")
    if not isinstance(intents, dict):
        return None
    ooc = intents.get("out_of_context")
    if not isinstance(ooc, dict) or ooc.get("present") is not True:
        return None
    reason = ooc.get("reason")
    confidence = ooc.get("confidence")
    return {
        "present": True,
        "confidence": float(confidence) if isinstance(confidence, int | float) else 0.0,
        "reason": str(reason).strip() if isinstance(reason, str) and reason.strip() else None,
        "source": "ai",
    }


# A photo caption the model is this unsure of (or that it flagged) is surfaced for a human to confirm.
CAPTION_LOW_CONFIDENCE_THRESHOLD = 0.5


def caption_review_marker(output: dict[str, Any]) -> dict[str, Any] | None:
    """Return a per-capture needs-review marker for an uncertain photo caption, or None.

    The §7 "AI unsure → tell the human" surface for captions, mirroring `out_of_context_marker`: a
    structured caption with low model `confidence` or explicit `uncertainties[]` raises a staff-facing
    review chip with a human-readable reason. Out-of-context has its own marker/chip, so it is not
    duplicated here; a blank caption (Basic / no gateway / manual-add) is never "uncertain".
    """
    text = output.get("text")
    if not isinstance(text, str) or not text.strip():
        return None
    uncertainties = [str(value).strip() for value in (output.get("uncertainties") or []) if isinstance(value, str) and value.strip()]
    confidence = output.get("confidence")
    has_confidence = isinstance(confidence, int | float) and not isinstance(confidence, bool)
    low_confidence = has_confidence and float(confidence) < CAPTION_LOW_CONFIDENCE_THRESHOLD
    if not low_confidence and not uncertainties:
        return None
    reason = uncertainties[0] if uncertainties else "Low-confidence caption — please review."
    return {
        "present": True,
        "reason": reason,
        "confidence": float(confidence) if has_confidence else None,
        "source": "ai",
    }


def should_apply_identity_assignment(
    *,
    has_session: bool,
    has_existing_patient: bool,
    assignment_basis: str | None,
) -> bool:
    """Decide whether extracted identity may be applied to the session.

    First identity on an unassigned visit is always applied (basis irrelevant). Once a
    patient is assigned, only an explicit (re)assignment instruction overrides it; an
    implicit mention is handled as a suggestion, not an application.
    """
    if not has_session:
        return False
    return not has_existing_patient or assignment_basis == "explicit"


NEAR_MATCH_SUGGEST_THRESHOLD = 0.78
# Fuzzy auto-apply line per match strictness (H3): the single-candidate confidence a fuzzy
# `possible_match` must clear to auto-apply. `strict` (None) = never; deterministic matches only.
# Fuzzy confidence is capped at 0.84 in patient_matching, so `balanced` catches a strong single
# variant (e.g. معاضد→معاصد @0.84) while `lenient` reaches down to the suggestion floor.
MATCH_STRICTNESS_AUTOAPPLY_THRESHOLD: dict[str, float | None] = {"strict": None, "balanced": 0.82, "lenient": 0.78}


def spoken_name_from_information(patient_information: dict[str, Any] | None) -> str | None:
    """The patient name as spoken/transcribed, for the 'Matched X · you said Y' surface (H4)."""
    if not isinstance(patient_information, dict):
        return None
    for key in ("raw_mentioned_name", "standardized_display_name", "full_name", "display_name"):
        value = patient_information.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _dominant_match_candidate(candidate: dict[str, Any] | None, *, threshold: float) -> dict[str, Any] | None:
    """Return the single high-confidence candidate from a match result, else None.

    None when the top candidate is below `threshold` or ties with the runner-up — an ambiguous
    or weak match stays a choose-patient decision rather than a one-tap target.
    """
    if not isinstance(candidate, dict):
        return None
    ranked = [c for c in (candidate.get("candidateSet") or []) if isinstance(c, dict) and c.get("patientId")]
    if not ranked:
        return None
    top = ranked[0]
    top_confidence = float(top.get("confidence") or 0.0)
    if top_confidence < threshold:
        return None
    if len(ranked) > 1 and float(ranked[1].get("confidence") or 0.0) >= top_confidence:
        return None  # tie at the top -> ambiguous
    return top


def suggested_reassignment_candidate(
    db: DbSession,
    *,
    tenant_id: uuid.UUID,
    session: Session,
    patient_information: dict[str, Any],
    policy_deferred: bool = False,
) -> dict[str, Any] | None:
    """Build an actionable but unapplied reassignment suggestion for an already-assigned visit.

    Used when a later capture only implicitly mentions a *different* patient: the assignment is not
    changed, but staff can apply the suggestion in one tap. A dominant fuzzy candidate is
    promoted to `patientId` so Apply reassigns to the existing patient rather than creating one.

    ``policy_deferred`` marks the AES-906 case: the capture *explicitly* asked to reassign, but the
    capturer's role isn't permitted to (AES-905), so it is routed to the owner as a suggestion
    rather than applied — never blocked. It carries `policyDeferred: True` + an owner-facing reason.

    Returns None when the implicit mention resolves to the patient already assigned to this visit:
    that is a confirmation/append, not a reassignment, so there is nothing to suggest. (This also
    suppresses the spurious chip when the model echoes the assigned patient's name back from the
    transcription context rather than from the spoken audio.)
    """
    match = ai_jobs_pkg.match_patient_from_patient_information(db, tenant_id=tenant_id, patient_information=patient_information)
    match = match if isinstance(match, dict) else {}
    patient_id = match.get("patientId")
    matched_name = match.get("displayName")
    if not patient_id:
        dominant = _dominant_match_candidate(match, threshold=NEAR_MATCH_SUGGEST_THRESHOLD)
        if dominant is not None:
            patient_id = dominant.get("patientId")
            matched_name = dominant.get("displayName")
    if patient_id is not None and session.patient_id is not None and str(patient_id) == str(session.patient_id):
        return None
    reason = (
        "A colleague's capture asked to reassign this visit, but their role can't reassign — "
        "suggested for the owner to apply."
        if policy_deferred
        else "Implicit patient mention on an already-assigned visit; suggested for review, not applied."
    )
    return {
        **match,
        "schemaVersion": "2026-06-02.patient-match-candidate.v1",
        "decision": "suggested_reassignment",
        "status": "suggested_reassignment",
        "appliedAutomatically": False,
        "policyDeferred": policy_deferred,
        "currentPatientId": str(session.patient_id) if session.patient_id else None,
        "patientId": patient_id,
        "displayName": matched_name,
        "matchedName": matched_name,
        "spokenName": spoken_name_from_information(patient_information),
        "reason": reason,
        "patientInformation": patient_information,
    }


def near_match_suggestion(candidate: dict[str, Any] | None, *, patient_information: dict[str, Any]) -> dict[str, Any] | None:
    """Turn a single confident fuzzy/`possible_match` into an actionable reassignment suggestion.

    Fuzzy matches are never auto-applied here (a near-spelling could be a different person), but a
    clear single front-runner is surfaced as a one-tap suggestion instead of a silent no-op —
    this covers ASR name variance (e.g. spoke معاصد, transcribed معاضد). Returns None when
    there is no dominant high-confidence candidate, so it stays a choose-patient decision.
    """
    if not isinstance(candidate, dict) or candidate.get("decision") != "possible_match":
        return None
    top = _dominant_match_candidate(candidate, threshold=NEAR_MATCH_SUGGEST_THRESHOLD)
    if top is None:
        return None
    matched_name = top.get("displayName")
    return {
        **candidate,
        "decision": "suggested_reassignment",
        "status": "suggested_reassignment",
        "appliedAutomatically": False,
        "patientId": top.get("patientId"),
        "displayName": matched_name,
        "matchedName": matched_name,
        "spokenName": spoken_name_from_information(patient_information),
        "reason": "Close name match found; confirm to apply.",
        "patientInformation": patient_information,
    }


def fuzzy_auto_apply_candidate(
    candidate: dict[str, Any] | None,
    *,
    strictness: str,
    assignment_basis: str | None,
) -> dict[str, Any] | None:
    """Return the single fuzzy candidate that match strictness permits auto-applying, else None.

    H3/H4: a partial (fuzzy) `possible_match` auto-applies only under `balanced`/`lenient`
    strictness, with an **explicit** reassignment instruction and a single dominant
    high-confidence candidate (no tie). The national-ID conflict guard and ambiguous routing
    win at every strictness level — a candidate carrying a national-ID conflict is never
    auto-applied, and an implicit mention is always a suggestion, not an application.
    """
    threshold = MATCH_STRICTNESS_AUTOAPPLY_THRESHOLD.get(strictness)
    if threshold is None:  # strict — deterministic matches only
        return None
    if assignment_basis != "explicit":  # implicit partial is always a suggestion
        return None
    if not isinstance(candidate, dict) or candidate.get("decision") != "possible_match":
        return None
    if NATIONAL_ID_CONFLICT_RISK in (candidate.get("risks") or []):
        return None
    top = _dominant_match_candidate(candidate, threshold=threshold)
    if top is None or NATIONAL_ID_CONFLICT_RISK in (top.get("risks") or []):
        return None
    return top
