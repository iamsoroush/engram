"""Smart patient search (aesthetics-Basic, AES-204).

Deterministic, Persian-orthography-aware, multi-field (name / phone / national ID / aliases), fast
at scale, **zero AI**. Reuses the confusable/transliteration normalization in
``patient_identity`` (Arabic↔Persian folding, digit normalization, Latin transliteration) and the
token-aware similarity in ``patient_matching`` — the same machinery the AI matcher uses — so a
receptionist's query finds the right record even across spelling/transliteration variance, and
doesn't split one Persian patient into many.

The ranking is a fixed deterministic ladder (exact identifier → exact name alias → prefix → fuzzy
token), so results are stable and explainable (every hit carries ``matchedOn`` + ``reason``).
"""

import uuid
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session as DbSession

from app.auth.dependencies import CurrentPrincipal
from app.models import Patient, PatientIdentifier, PatientStatus
from app.services.patient_identity import (
    alias_tokens,
    consonant_skeleton,
    normalize_email,
    normalize_iranian_phone,
    normalize_national_id,
    normalize_text_key,
    normalized_aliases_for_value,
    search_keys_for_query,
    transliterate_persian_to_latin,
)
from app.services.patient_matching import _name_similarity
from app.services.patients import patient_payload

SEARCH_SCHEMA_VERSION = "2026-06-12.patient-search.v1"
# How many candidate patients to score in Python after the indexed DB gather. Bounds work even on a
# large tenant: the SQL pre-filter (exact-in + prefix + column ilike) only ever returns matches.
MAX_SCORED_CANDIDATES = 200
# Below this token similarity a name is not considered a match at all (mirrors the AI matcher's
# fuzzy floor, 0.68) — keeps unrelated names out of search results.
FUZZY_NAME_FLOOR = 0.68
ALIAS_IDENTIFIER_TYPES = ("normalized_alias", "normalized_name")


class _QueryKeys:
    """Normalized projections of a raw search query, computed once per request."""

    def __init__(self, query: str) -> None:
        self.raw = query.strip()
        self.name_key = normalize_text_key(query)
        self.latin_key = transliterate_persian_to_latin(query)
        self.aliases = set(normalized_aliases_for_value(query))
        self.tokens = [token for token in alias_tokens(self.aliases) if token]
        self.national_id = normalize_national_id(query)
        self.phone = normalize_iranian_phone(query)
        self.email = normalize_email(query)
        # All deterministic identifier keys worth an exact lookup (used to build the SQL gather).
        self.identifier_keys = [key for key in search_keys_for_query(query) if key]

    @property
    def name_candidates(self) -> set[str]:
        keys = set(self.aliases)
        if self.name_key:
            keys.add(self.name_key)
        if self.latin_key:
            keys.add(self.latin_key)
        return keys


def _match_patient(
    keys: _QueryKeys,
    *,
    patient: Patient,
    identifiers: list[PatientIdentifier],
) -> dict[str, Any] | None:
    """Score one candidate patient against the query; return its best match or ``None``.

    The ladder is deterministic and the first (highest) rung that fires wins. ``score`` is in
    ``[0, 1]``; ``matchedOn`` names the field that won so the UI can explain the hit.
    """
    national_ids = {idf.normalized_value for idf in identifiers if idf.identifier_type == "national_id" and idf.normalized_value}
    phones = {idf.normalized_value for idf in identifiers if idf.identifier_type == "phone" and idf.normalized_value}
    emails = {idf.normalized_value for idf in identifiers if idf.identifier_type == "email" and idf.normalized_value}
    alias_values = {idf.normalized_value for idf in identifiers if idf.identifier_type in ALIAS_IDENTIFIER_TYPES and idf.normalized_value}
    # Fall back to the patient's own columns when no identifier row exists yet.
    if patient.phone and (normalized := normalize_iranian_phone(patient.phone)):
        phones.add(normalized)
    if patient.email and (normalized := normalize_email(patient.email)):
        emails.add(normalized)
    display_alias = normalize_text_key(patient.display_name)
    if display_alias:
        alias_values.add(display_alias)

    if keys.national_id and keys.national_id in national_ids:
        return {"score": 1.0, "matchedOn": ["national_id"], "reason": "Exact national ID match."}
    if keys.phone and keys.phone in phones:
        return {"score": 0.98, "matchedOn": ["phone"], "reason": "Exact phone match."}
    if keys.email and keys.email in emails:
        return {"score": 0.97, "matchedOn": ["email"], "reason": "Exact email match."}

    query_names = keys.name_candidates
    if query_names & alias_values:
        return {"score": 0.95, "matchedOn": ["name"], "reason": "Exact name match (orthography-folded)."}
    if query_names and any(
        alias.startswith(q) or q.startswith(alias) for alias in alias_values for q in query_names if alias and q
    ):
        return {"score": 0.85, "matchedOn": ["name_prefix"], "reason": "Name starts with the query."}

    if keys.name_key and alias_values:
        best = max(_name_similarity(keys.name_key, alias) for alias in alias_values)
        if best >= FUZZY_NAME_FLOOR:
            return {
                "score": round(min(0.84, best), 3),
                "matchedOn": ["name_fuzzy"],
                "reason": "Close name match (first/last-name or transliteration variance).",
            }

    # Vowel-tolerant (consonant-skeleton) match: «neg»/«negar» → «نگار» (transliterated «ngar» → skel
    # «ngr»). One skeleton being a prefix of the other catches both partial and full typed names.
    query_skeleton = consonant_skeleton(keys.raw)
    if query_skeleton and len(query_skeleton) >= 2:
        for alias in alias_values:
            alias_skeleton = consonant_skeleton(alias)
            if alias_skeleton and (alias_skeleton.startswith(query_skeleton) or query_skeleton.startswith(alias_skeleton)):
                return {"score": 0.72, "matchedOn": ["name_skeleton"], "reason": "Transliteration / vowel-variance name match."}

    # Partial contact: the typed digits are a fragment of a stored number (e.g. last 4 of a phone).
    digit_query = keys.national_id or (keys.phone.lstrip("+") if keys.phone else None)
    if digit_query and len(digit_query) >= 4:
        for value in (*national_ids, *(phone.lstrip("+") for phone in phones)):
            if digit_query in value:
                return {"score": 0.6, "matchedOn": ["contact_partial"], "reason": "Partial phone/national ID match."}
    return None


def _candidate_patient_ids(db: DbSession, *, tenant_id: uuid.UUID, keys: _QueryKeys) -> set[uuid.UUID]:
    """Gather candidate patient IDs using only index-friendly predicates."""
    ids: set[uuid.UUID] = set()
    identifier_predicates = []
    if keys.identifier_keys:
        identifier_predicates.append(PatientIdentifier.normalized_value.in_(keys.identifier_keys))
    # Contains-scan per token so a partial mention finds the full-named patient — a last-name-only
    # query ("نظری") must still surface "محمدرضا نظری". This mirrors the AI matcher's fuzzy gather;
    # the actual ranking still happens in `_match_patient`, this only widens the candidate net.
    identifier_predicates.extend(PatientIdentifier.normalized_value.ilike(f"%{token}%") for token in keys.tokens)
    # Vowel-tolerant gather: Persian transliteration drops short vowels («نگار»→«ngar») but users type
    # them («negar»). Match consonant skeletons so the typed name still surfaces the patient; the
    # ranking in `_match_patient` still decides the score (this only widens the candidate net).
    skeleton = consonant_skeleton(keys.raw)
    if skeleton:
        identifier_predicates.append(
            func.regexp_replace(PatientIdentifier.normalized_value, "[aeiouy]", "", "g").ilike(f"%{skeleton}%")
        )
    if identifier_predicates:
        rows = db.execute(
            select(PatientIdentifier.patient_id)
            .where(PatientIdentifier.tenant_id == tenant_id, or_(*identifier_predicates))
            .limit(MAX_SCORED_CANDIDATES)
        ).scalars()
        ids.update(rows)

    pattern = f"%{keys.raw}%"
    direct = db.execute(
        select(Patient.id).where(
            Patient.tenant_id == tenant_id,
            Patient.status == PatientStatus.active,
            or_(
                Patient.display_name.ilike(pattern),
                Patient.legal_first_name.ilike(pattern),
                Patient.legal_last_name.ilike(pattern),
                Patient.phone.ilike(pattern),
                Patient.email.ilike(pattern),
            ),
        ).limit(MAX_SCORED_CANDIDATES)
    ).scalars()
    ids.update(direct)
    return ids


def smart_search_patients(
    db: DbSession,
    principal: CurrentPrincipal,
    *,
    query: str | None,
    limit: int = 20,
) -> dict[str, Any]:
    """Return deterministically-ranked patient matches for a search query (AES-204).

    Args:
        db: Active database session.
        principal: The authenticated staff principal (scopes the search to its tenant).
        query: Free-text query — a name (any script), phone, national ID, or alias. Blank/None
            returns the most recently updated patients (a useful default list).
        limit: Maximum number of ranked results to return.

    Returns:
        ``{"schemaVersion", "query", "items": [...], "total"}`` where each item is the standard
        patient payload plus ``score`` (0–1), ``matchedOn`` (the winning field(s)), and ``reason``.
        Items are sorted by score, then most-recently-updated.
    """
    from app.services.caseload import caseload_patient_condition

    capped_limit = max(1, min(limit, 100))
    cleaned = (query or "").strip()
    # Federated caseloads (therapy): scope smart search to the clinician's own clients (no-op elsewhere).
    caseload = caseload_patient_condition(db, principal)
    if not cleaned:
        recent_statement = (
            select(Patient)
            .where(Patient.tenant_id == principal.tenant_id, Patient.status == PatientStatus.active)
        )
        if caseload is not None:
            recent_statement = recent_statement.where(caseload)
        patients = db.execute(
            recent_statement.order_by(Patient.updated_at.desc()).limit(capped_limit)
        ).scalars().all()
        items = [{**patient_payload(patient), "score": None, "matchedOn": [], "reason": "Recent patient."} for patient in patients]
        return {"schemaVersion": SEARCH_SCHEMA_VERSION, "query": cleaned, "items": items, "total": len(items)}

    keys = _QueryKeys(cleaned)
    candidate_ids = _candidate_patient_ids(db, tenant_id=principal.tenant_id, keys=keys)
    if not candidate_ids:
        return {"schemaVersion": SEARCH_SCHEMA_VERSION, "query": cleaned, "items": [], "total": 0}

    candidate_id_list = list(candidate_ids)[:MAX_SCORED_CANDIDATES]
    candidate_statement = select(Patient).where(
        Patient.tenant_id == principal.tenant_id,
        Patient.status == PatientStatus.active,
        Patient.id.in_(candidate_id_list),
    )
    if caseload is not None:
        candidate_statement = candidate_statement.where(caseload)
    patients = db.execute(candidate_statement).scalars().all()
    identifiers_by_patient: dict[uuid.UUID, list[PatientIdentifier]] = {}
    for identifier in db.execute(
        select(PatientIdentifier).where(
            PatientIdentifier.tenant_id == principal.tenant_id,
            PatientIdentifier.patient_id.in_(candidate_id_list),
        )
    ).scalars():
        identifiers_by_patient.setdefault(identifier.patient_id, []).append(identifier)

    scored: list[tuple[dict[str, Any], Patient]] = []
    for patient in patients:
        match = _match_patient(keys, patient=patient, identifiers=identifiers_by_patient.get(patient.id, []))
        if match is not None:
            scored.append((match, patient))
    scored.sort(
        key=lambda item: (item[0]["score"], item[1].updated_at or item[1].created_at),
        reverse=True,
    )
    items = [
        {**patient_payload(patient), "score": match["score"], "matchedOn": match["matchedOn"], "reason": match["reason"]}
        for match, patient in scored[:capped_limit]
    ]
    return {"schemaVersion": SEARCH_SCHEMA_VERSION, "query": cleaned, "items": items, "total": len(scored)}
