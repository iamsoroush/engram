import uuid
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session as DbSession

from app.models import Patient, PatientIdentifier, PatientStatus
from app.services.patient_identity import (
    alias_tokens,
    normalize_email,
    normalize_iranian_phone,
    normalize_national_id,
    normalized_aliases_for_value,
)

MATCH_SCHEMA_VERSION = "2026-06-02.patient-match-candidate.v1"
MAX_BACKEND_CANDIDATES = 5


@dataclass
class MatchCandidate:
    patient_id: uuid.UUID
    display_name: str
    confidence: float
    matched_on: list[str]
    reason: str
    risks: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)


def _patient_information_values(patient_information: dict[str, Any]) -> dict[str, Any]:
    names = []
    for key in ("standardized_display_name", "raw_mentioned_name", "full_name", "display_name"):
        value = patient_information.get(key)
        if isinstance(value, str) and value.strip():
            names.append(value.strip())
    alternates = patient_information.get("alternate_transliterations")
    if isinstance(alternates, list):
        names.extend(value.strip() for value in alternates if isinstance(value, str) and value.strip())
    return {
        "names": list(dict.fromkeys(names)),
        "national_id": normalize_national_id(patient_information.get("national_id")),
        "phone": normalize_iranian_phone(patient_information.get("phone")),
        "email": normalize_email(patient_information.get("email")),
    }


def _candidate_payload(candidate: MatchCandidate) -> dict[str, Any]:
    return {
        "patientId": str(candidate.patient_id),
        "displayName": candidate.display_name,
        "confidence": round(candidate.confidence, 3),
        "matchedOn": candidate.matched_on,
        "reason": candidate.reason,
        "risks": candidate.risks,
        "evidence": candidate.evidence,
    }


def _candidate_from_identifier(
    db: DbSession,
    *,
    identifier: PatientIdentifier,
    confidence: float,
    matched_on: str,
    reason: str,
    risks: list[str] | None = None,
) -> MatchCandidate | None:
    patient = db.execute(
        select(Patient).where(
            Patient.id == identifier.patient_id,
            Patient.tenant_id == identifier.tenant_id,
            Patient.status == PatientStatus.active,
        )
    ).scalar_one_or_none()
    if patient is None:
        return None
    return MatchCandidate(
        patient_id=patient.id,
        display_name=patient.display_name,
        confidence=confidence,
        matched_on=[matched_on],
        reason=reason,
        risks=risks or [],
        evidence={
            "identifierType": identifier.identifier_type,
            "identifierValue": identifier.identifier_value,
            "normalizedValue": identifier.normalized_value,
        },
    )


def _exact_identifier_candidates(
    db: DbSession,
    *,
    tenant_id: uuid.UUID,
    identifier_type: str,
    normalized_value: str,
    matched_on: str,
    reason: str,
) -> list[MatchCandidate]:
    identifiers = list(
        db.execute(
            select(PatientIdentifier)
            .where(
                PatientIdentifier.tenant_id == tenant_id,
                PatientIdentifier.identifier_type == identifier_type,
                PatientIdentifier.normalized_value == normalized_value,
            )
            .order_by(PatientIdentifier.created_at.desc())
            .limit(MAX_BACKEND_CANDIDATES + 1)
        ).scalars()
    )
    duplicate_risk = ["Multiple patients share this identifier. Staff must confirm before assignment."] if len(identifiers) > 1 else []
    candidates = [
        candidate
        for identifier in identifiers[:MAX_BACKEND_CANDIDATES]
        if (
            candidate := _candidate_from_identifier(
                db,
                identifier=identifier,
                confidence=1.0 if identifier_type == "national_id" else 0.97,
                matched_on=matched_on,
                reason=reason,
                risks=duplicate_risk,
            )
        )
        is not None
    ]
    return candidates


def _exact_alias_candidates(
    db: DbSession,
    *,
    tenant_id: uuid.UUID,
    aliases: list[str],
) -> list[MatchCandidate]:
    if not aliases:
        return []
    identifiers = list(
        db.execute(
            select(PatientIdentifier)
            .where(
                PatientIdentifier.tenant_id == tenant_id,
                PatientIdentifier.identifier_type.in_(["normalized_alias", "normalized_name"]),
                PatientIdentifier.normalized_value.in_(aliases),
            )
            .order_by(PatientIdentifier.created_at.desc())
            .limit(MAX_BACKEND_CANDIDATES)
        ).scalars()
    )
    return [
        candidate
        for identifier in identifiers
        if (
            candidate := _candidate_from_identifier(
                db,
                identifier=identifier,
                confidence=0.88,
                matched_on="normalized_alias",
                reason="The extracted name exactly matched a deterministic normalized patient alias.",
            )
        )
        is not None
    ]


def _name_similarity(query: str, candidate: str) -> float:
    """Token-aware similarity between two normalized name strings.

    Returns the stronger of whole-string similarity and token-level containment. The token
    score matches each token of the *smaller* name against its best counterpart in the larger
    name and averages over the smaller set, so a last-name-only (or first-name-only) mention
    still scores ~1.0 against the patient's full stored name — and the reverse holds when the
    stored name is the partial one. This is what lets "نظری"/"Nazari" find "Mohammadreza
    Nazari" even though whole-string ``SequenceMatcher`` drops below threshold on the length
    gap. Per-token fuzzy matching also tolerates transliteration drift (e.g. "nazari" vs
    "nazary").
    """
    full_ratio = SequenceMatcher(None, query, candidate).ratio()
    query_tokens = alias_tokens([query])
    candidate_tokens = alias_tokens([candidate])
    if not query_tokens or not candidate_tokens:
        return full_ratio
    smaller, larger = sorted((query_tokens, candidate_tokens), key=len)
    token_score = sum(max(SequenceMatcher(None, token, other).ratio() for other in larger) for token in smaller) / len(smaller)
    return max(full_ratio, token_score)


def _fuzzy_alias_candidates(
    db: DbSession,
    *,
    tenant_id: uuid.UUID,
    aliases: list[str],
) -> list[MatchCandidate]:
    tokens = alias_tokens(aliases)
    if not tokens:
        return []
    identifiers = list(
        db.execute(
            select(PatientIdentifier)
            .where(
                PatientIdentifier.tenant_id == tenant_id,
                PatientIdentifier.identifier_type.in_(["normalized_alias", "normalized_name"]),
                or_(*(PatientIdentifier.normalized_value.ilike(f"%{token}%") for token in tokens)),
            )
            .order_by(PatientIdentifier.created_at.desc())
            .limit(25)
        ).scalars()
    )
    by_patient: dict[uuid.UUID, MatchCandidate] = {}
    for identifier in identifiers:
        if not identifier.normalized_value:
            continue
        score = max(_name_similarity(alias, identifier.normalized_value) for alias in aliases)
        if score < 0.68:
            continue
        candidate = _candidate_from_identifier(
            db,
            identifier=identifier,
            confidence=min(0.84, max(0.45, score)),
            matched_on="fuzzy_alias",
            reason="The extracted name overlaps a deterministic patient alias, including partial first/last-name matches.",
            risks=["Name-only or partial-name matches can confuse transliterations, relatives, or people who share a first or last name."],
        )
        if candidate is None:
            continue
        previous = by_patient.get(candidate.patient_id)
        if previous is None or candidate.confidence > previous.confidence:
            by_patient[candidate.patient_id] = candidate
    return sorted(by_patient.values(), key=lambda candidate: candidate.confidence, reverse=True)[:MAX_BACKEND_CANDIDATES]


NATIONAL_ID_CONFLICT_RISK = "The extracted national ID does not match this patient's national ID. Staff must confirm before assignment."


def _stored_national_ids(db: DbSession, *, tenant_id: uuid.UUID, patient_id: uuid.UUID) -> set[str]:
    return {
        value
        for value in db.execute(
            select(PatientIdentifier.normalized_value).where(
                PatientIdentifier.tenant_id == tenant_id,
                PatientIdentifier.patient_id == patient_id,
                PatientIdentifier.identifier_type == "national_id",
            )
        ).scalars()
        if value
    }


def _national_id_conflict(
    db: DbSession,
    *,
    tenant_id: uuid.UUID,
    candidate: MatchCandidate,
    provided_national_id: str | None,
) -> bool:
    """Whether a non-national-ID match is contradicted by a provided national ID.

    National ID is the strongest key. If the visit provides one and the name/contact-matched
    patient already stores a *different* national ID, the deterministic match is unsafe and
    must go to staff review rather than auto-assignment.
    """
    if not provided_national_id:
        return False
    stored = _stored_national_ids(db, tenant_id=tenant_id, patient_id=candidate.patient_id)
    return bool(stored) and provided_national_id not in stored


def _result(
    *,
    decision: str,
    candidates: list[MatchCandidate],
    matched_on: list[str],
    reason: str,
    patient_information: dict[str, Any],
    risks: list[str] | None = None,
) -> dict[str, Any]:
    top = candidates[0] if candidates else None
    llm_eligible = decision == "possible_match" and len(candidates) > 1
    return {
        "schemaVersion": MATCH_SCHEMA_VERSION,
        "decision": decision,
        "status": decision,
        "patientId": str(top.patient_id) if top and decision == "matched" else None,
        "displayName": top.display_name if top and decision == "matched" else None,
        "confidence": round(top.confidence, 3) if top else 0.0,
        "matchedOn": matched_on,
        "reason": reason,
        "risks": risks or [],
        "candidateSet": [_candidate_payload(candidate) for candidate in candidates[:MAX_BACKEND_CANDIDATES]],
        "llmRanking": {
            "eligible": llm_eligible,
            "status": "not_configured",
            "candidateCount": len(candidates[:MAX_BACKEND_CANDIDATES]),
            "maxCandidates": MAX_BACKEND_CANDIDATES,
            "note": "Backend selected this capped candidate set; no whole-table LLM search is allowed.",
        },
        "source": "deterministic-patient-matching",
        "patientInformation": patient_information,
    }


def match_patient_from_patient_information(
    db: DbSession,
    *,
    tenant_id: uuid.UUID,
    patient_information: dict[str, Any],
) -> dict[str, Any] | None:
    """Return a reviewable patient-match proposal from structured identity data."""
    values = _patient_information_values(patient_information)
    if values["national_id"]:
        candidates = _exact_identifier_candidates(
            db,
            tenant_id=tenant_id,
            identifier_type="national_id",
            normalized_value=values["national_id"],
            matched_on="national_id",
            reason="The extracted national ID exactly matched an existing patient identifier.",
        )
        if candidates:
            return _result(
                decision="matched",
                candidates=candidates,
                matched_on=["national_id"],
                reason="Exact national ID match selected deterministically.",
                patient_information=patient_information,
                risks=candidates[0].risks,
            )

    contact_candidates: list[MatchCandidate] = []
    if values["phone"]:
        contact_candidates.extend(
            _exact_identifier_candidates(
                db,
                tenant_id=tenant_id,
                identifier_type="phone",
                normalized_value=values["phone"],
                matched_on="phone",
                reason="The extracted phone number exactly matched an existing patient identifier.",
            )
        )
    if values["email"]:
        contact_candidates.extend(
            _exact_identifier_candidates(
                db,
                tenant_id=tenant_id,
                identifier_type="email",
                normalized_value=values["email"],
                matched_on="email",
                reason="The extracted email exactly matched an existing patient identifier.",
            )
        )
    if contact_candidates:
        decision = "matched"
        risks = list(contact_candidates[0].risks)
        if _national_id_conflict(db, tenant_id=tenant_id, candidate=contact_candidates[0], provided_national_id=values["national_id"]):
            decision = "possible_match"
            risks = [*risks, NATIONAL_ID_CONFLICT_RISK]
        return _result(
            decision=decision,
            candidates=contact_candidates[:MAX_BACKEND_CANDIDATES],
            matched_on=contact_candidates[0].matched_on,
            reason="Exact contact match selected deterministically.",
            patient_information=patient_information,
            risks=risks,
        )

    aliases = list(dict.fromkeys(alias for name in values["names"] for alias in normalized_aliases_for_value(name)))
    exact_alias = _exact_alias_candidates(db, tenant_id=tenant_id, aliases=aliases)
    if exact_alias:
        decision = "matched" if len({candidate.patient_id for candidate in exact_alias}) == 1 else "possible_match"
        risks = [] if decision == "matched" else ["Multiple patients share this normalized alias."]
        if decision == "matched" and _national_id_conflict(
            db, tenant_id=tenant_id, candidate=exact_alias[0], provided_national_id=values["national_id"]
        ):
            decision = "possible_match"
            risks = [NATIONAL_ID_CONFLICT_RISK]
        return _result(
            decision=decision,
            candidates=exact_alias,
            matched_on=["normalized_alias"],
            reason="Extracted name matched a normalized alias; staff should review before assignment.",
            patient_information=patient_information,
            risks=risks,
        )

    fuzzy = _fuzzy_alias_candidates(db, tenant_id=tenant_id, aliases=aliases)
    if fuzzy:
        return _result(
            decision="possible_match",
            candidates=fuzzy,
            matched_on=["fuzzy_alias"],
            reason="Fuzzy alias search found possible matches for review.",
            patient_information=patient_information,
            risks=["Fuzzy name matches are not safe enough for automatic assignment."],
        )

    if not any([values["national_id"], values["phone"], values["email"], values["names"]]):
        return _result(
            decision="insufficient_info",
            candidates=[],
            matched_on=[],
            reason="No structured patient identity fields were available to match.",
            patient_information=patient_information,
            risks=["The visit needs staff input if a patient must be assigned."],
        )
    return _result(
        decision="no_match",
        candidates=[],
        matched_on=[],
        reason="No existing patient matched the structured identity information.",
        patient_information=patient_information,
        risks=["Staff may need to search manually, create a patient, or keep the visit unassigned."],
    )


def match_patient_from_metadata(
    db: DbSession,
    *,
    tenant_id: uuid.UUID,
    extracted_metadata: dict[str, Any],
) -> dict[str, Any] | None:
    """Find a reviewable patient-match proposal from generated metadata."""
    patient_info = extracted_metadata.get("patient_information")
    if not isinstance(patient_info, dict):
        return None
    return match_patient_from_patient_information(db, tenant_id=tenant_id, patient_information=patient_info)
