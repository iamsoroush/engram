"""Therapy session synthesis (Spine A, therapy vertical).

Therapy is **narrative-first and longitudinal**: the value is continuity of understanding across a
relationship, not a "treatment performed" structure. This module is the therapy branch of the
report-synthesis path — it turns a session's captures (note-first; decorated notes + optional audio
recaps) into:

- a **two-plane** session summary — a **shareable** progress-note (DAP / SOAP / BIRP) the therapist
  may release to the client, and a **private** plane (reflections + any audio transcript) that never
  leaves the clinician;
- a live **"Session so far"** running synthesis that updates as captures land;
- cross-session signals: recurring **themes** and an **assisted, clinician-confirmed risk** flag.

See ``docs/ux/redesign-therapy.md`` (§1.2 capture model, §5.3 two planes, §7 privacy) and the design
foundation ``docs/ux/redesign-foundation.md`` §1 (therapy = single plan, the AI *is* the value).

**v1 is deterministic** — it assembles the capture text (audio ``transcription`` is the per-capture
AI; notes are a raw passthrough) into the format's sections by light sentence routing, exactly as the
aesthetics live report is a deterministic assembly of captures today. ``THERAPY_SYNTHESIS_PROMPTS``
holds the prompt contracts a real LLM synthesizer will
use to replace this assembler without changing the stored shape (the ``therapy`` block below).

Privacy invariant (foundation §7, redesign §7): the **report model carries only the shareable
plane**, so any export / patient payload that renders ``report_model`` / ``generated_report`` can
never leak the private plane. The private plane lives in the ``therapy`` metadata block and the
clinician-only audio transcripts.
"""

import re
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session as DbSession

from app.auth.dependencies import CurrentPrincipal
from app.models import Capture, CaptureType, OrganizationSource, Session, SessionStatus
from app.services.reporting import REPORT_MODEL_VERSION, get_report_template

THERAPY_SYNTHESIS_VERSION = "2026-06-13.therapy-synthesis.v1"

THERAPY_REPORT_FORMATS = ("dap", "soap", "birp")
DEFAULT_THERAPY_FORMAT = "dap"

# Each shareable-plane format → its ordered (section id, display title) sections. The *content* is
# the same captured material re-projected per format (no data loss across a switch), per redesign §5.3.
FORMAT_SECTIONS: dict[str, tuple[tuple[str, str], ...]] = {
    "dap": (("data", "Data"), ("assessment", "Assessment"), ("plan", "Plan")),
    "soap": (("subjective", "Subjective"), ("objective", "Objective"), ("assessment", "Assessment"), ("plan", "Plan")),
    "birp": (("behavior", "Behavior"), ("intervention", "Intervention"), ("response", "Response"), ("plan", "Plan")),
}

# The section each format treats as its primary "what the client reported" bucket (unrouted content
# lands here) and the section that collects clinician-action/plan content.
_PRIMARY_SECTION: dict[str, str] = {"dap": "data", "soap": "subjective", "birp": "behavior"}
_PLAN_SECTION = "plan"

# Light, transparent sentence-routing cues (deterministic stand-in for LLM synthesis). A real
# synthesizer replaces this with the prompts below; the stored shape is identical.
_PLAN_CUES = ("plan to", "plan is", "plans to", "the plan", "next session", "next time", "next week",
              "next visit", "follow up", "follow-up", "homework", "refer", "referral", "schedule",
              "recommend", "will try", "intend", "agreed to", "going to try", "goal", "between now")
_ASSESSMENT_CUES = ("appears", "presents", "progress", "improving", "worsening", "stuck", "impression",
                    "insight", "rapport", "engaged", "ambivalent", "resistant")
_OBJECTIVE_CUES = ("observed", "affect", "presented", "tearful", "agitated", "calm", "flat", "noted",
                   "eye contact", "appeared")
_INTERVENTION_CUES = ("explored", "introduced", "practiced", "used", "applied", "cbt", "reframe",
                      "validated", "psychoeducation", "technique", "intervention", "worked on")

# Recurring-theme lexicon (research §6 / redesign A1, C2): therapy topics worth surfacing across
# sessions. Deterministic v1; a real synthesizer derives these from memory.
_THEME_LEXICON: dict[str, tuple[str, ...]] = {
    "anxiety": ("anxiety", "anxious", "panic", "worry", "worried", "nervous"),
    "depression": ("depression", "depressed", "low mood", "hopeless", "down"),
    "boundaries": ("boundary", "boundaries", "assertive", "saying no"),
    "family": ("mother", "father", "parent", "family", "sister", "brother", "sibling"),
    "relationship": ("partner", "relationship", "marriage", "divorce", "dating", "spouse"),
    "work": ("work", "job", "career", "boss", "burnout", "workplace"),
    "sleep": ("sleep", "insomnia", "nightmare", "rest"),
    "grief": ("grief", "loss", "bereavement", "death", "mourning"),
    "anger": ("anger", "angry", "rage", "irritable", "frustrated"),
    "self-esteem": ("self-esteem", "self esteem", "worthless", "confidence", "self-worth"),
    "trauma": ("trauma", "ptsd", "flashback", "abuse"),
}

# Assisted risk-detection cues. A hit only *suggests* a flag — risk is always clinician-confirmed and
# dated (redesign §5.3 / C3), never auto-set.
_RISK_CUES = ("suicid", "self-harm", "self harm", "kill myself", "end my life", "hopeless",
              "harm to", "crisis", "overdose", "hurt myself")

TherapyFormat = Literal["dap", "soap", "birp"]


# --- Prompt contracts for a future LLM synthesizer (not used by the deterministic v1) -------------
# These document what a real synthesizer must produce so it can drop in without changing the stored
# `therapy` block. Mirrors how aesthetics keeps a stable session-processing contract.
THERAPY_SYNTHESIS_PROMPTS: dict[str, str] = {
    "system": (
        "You are Engram, a calm clinical assistant for a psychotherapy practice. You maintain a "
        "client's session memory. Synthesize the therapist's in-session notes and any audio recap "
        "into a progress note. Never invent clinical content, names, or risk that is not in the "
        "captures. Two planes are strictly separated: the SHAREABLE plane is a releasable progress "
        "note; the PRIVATE plane holds the therapist's reflections/hypotheses and is never exported."
    ),
    "shareable": (
        "Write the shareable progress note in the requested format ({format}). Reproject the same "
        "captured content into the format's sections; do not drop or invent content. Keep it prose, "
        "not a form. Sections: {sections}."
    ),
    "session_so_far": (
        "Write a one-line running synthesis of what has been captured so far this session, plus a "
        "2-3 sentence narrative. Track which of the brief's threads have been covered vs. remain open."
    ),
    "private": (
        "Summarize the therapist's reflections and clinical hypotheses for the PRIVATE plane only. "
        "This is never shared with the client or exported."
    ),
    "risk": (
        "If, and only if, the captures contain explicit risk content (suicidality, self-harm, harm "
        "to others, crisis), surface a SUGGESTED risk flag with the quoted cue. Never confirm risk "
        "yourself — the clinician confirms and dates it."
    ),
}


def _generated_text(value: Any) -> str | None:
    """Return generated/display text from a capture metadata field ({'text': ...} or a string)."""
    if isinstance(value, dict) and isinstance(value.get("text"), str):
        text = value["text"].strip()
        return text or None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return None


def _capture_text(capture: Capture) -> str | None:
    """Return a therapy capture's clinical text: decorated note, audio transcript, or photo caption."""
    metadata = capture.capture_metadata if isinstance(capture.capture_metadata, dict) else {}
    if capture.capture_type == CaptureType.audio:
        return _generated_text(metadata.get("transcript"))
    if capture.capture_type == CaptureType.note:
        # Notes are a pure passthrough (decoration removed): use the raw captured text.
        return _generated_text(metadata.get("detail"))
    if capture.capture_type == CaptureType.photo:
        return _generated_text(metadata.get("caption"))
    return None


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?؟。])\s+", text.strip())
    return [part.strip() for part in parts if part.strip()]


def _route_sentence(sentence: str, fmt: str) -> str:
    """Route a sentence to a section id for the format (deterministic synthesis stand-in)."""
    lowered = sentence.lower()
    if any(cue in lowered for cue in _PLAN_CUES):
        return _PLAN_SECTION
    if fmt == "soap" and any(cue in lowered for cue in _OBJECTIVE_CUES):
        return "objective"
    if fmt == "birp" and any(cue in lowered for cue in _INTERVENTION_CUES):
        return "intervention"
    if fmt == "birp" and any(cue in lowered for cue in _ASSESSMENT_CUES):
        return "response"
    if any(cue in lowered for cue in _ASSESSMENT_CUES):
        return "assessment" if fmt in {"dap", "soap"} else "response"
    return _PRIMARY_SECTION[fmt]


def normalize_therapy_format(value: Any) -> str:
    """Return a supported therapy report format, defaulting to DAP."""
    if isinstance(value, str) and value.strip().lower() in THERAPY_REPORT_FORMATS:
        return value.strip().lower()
    return DEFAULT_THERAPY_FORMAT


def therapy_format_from_session(session: Session) -> str:
    """Read the therapist-selected report format from the session (DAP default)."""
    metadata = session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {}
    return normalize_therapy_format(metadata.get("therapy_format"))


def _detect_themes(texts: list[str]) -> list[dict[str, Any]]:
    blob = " ".join(texts).lower()
    themes: list[dict[str, Any]] = []
    for label, cues in _THEME_LEXICON.items():
        mentions = sum(blob.count(cue) for cue in cues)
        if mentions:
            themes.append({"label": label, "mentions": mentions})
    themes.sort(key=lambda theme: theme["mentions"], reverse=True)
    return themes[:4]


def _detect_risk_cue(texts: list[str]) -> str | None:
    for text in texts:
        lowered = text.lower()
        for cue in _RISK_CUES:
            if cue in lowered:
                return next((sentence for sentence in _sentences(text) if cue in sentence.lower()), text.strip())
    return None


def _section_bodies(captures: list[Capture], fmt: str) -> dict[str, list[str]]:
    """Route captured sentences into the format's sections (the SHAREABLE plane).

    Privacy invariant (§7 / E2): the **verbatim audio transcript is the most-private object and is
    never exported**, so audio is excluded here — the shareable progress note is built from the
    note-first, clinician-filtered captures (decorated notes / photo captions). The audio recap still
    enriches the private plane (``planes.private.audioTranscripts``). A future LLM synthesizer will
    fold a *paraphrased* (non-verbatim) reflection of the recap into the shareable note; the
    deterministic v1 keeps the boundary strict by leaving verbatim audio out of the shareable plane.
    """
    buckets: dict[str, list[str]] = {section_id: [] for section_id, _ in FORMAT_SECTIONS[fmt]}
    for capture in captures:
        if capture.capture_type == CaptureType.audio:
            continue
        text = _capture_text(capture)
        if not text:
            continue
        for sentence in _sentences(text):
            buckets[_route_sentence(sentence, fmt)].append(sentence)
    return buckets


def _shareable_sections(buckets: dict[str, list[str]], fmt: str, themes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    for section_id, title in FORMAT_SECTIONS[fmt]:
        body_sentences = buckets.get(section_id, [])
        if section_id == "assessment" and not body_sentences:
            # A light synthesized impression so Assessment is never blank (clearly synthesized, ✨).
            theme_text = ", ".join(theme["label"] for theme in themes)
            body_sentences = [
                "Session synthesized from captured notes."
                + (f" Recurring themes: {theme_text}." if theme_text else "")
            ]
        if section_id == _PLAN_SECTION and not body_sentences:
            body_sentences = ["No explicit plan was captured; to be set with the client."]
        body = " ".join(body_sentences)
        sections.append({"id": section_id, "title": title, "blocks": [{"type": "paragraph", "text": body}] if body else []})
    return sections


def build_therapy_report_model(session: Session, captures: list[Capture], *, fmt: str | None = None) -> dict[str, Any]:
    """Build the SHAREABLE-plane structured report model for a therapy session.

    The model carries only the shareable plane (the private plane never enters ``report_model``), so
    any consumer that renders the report cannot leak the private layer.
    """
    resolved = normalize_therapy_format(fmt if fmt is not None else therapy_format_from_session(session))
    template = get_report_template(session.report_template_key)
    texts = [text for text in (_capture_text(capture) for capture in captures) if text]
    buckets = _section_bodies(captures, resolved)
    themes = _detect_themes(texts)
    return {
        "schemaVersion": REPORT_MODEL_VERSION,
        "templateKey": template.key,
        "title": session.title or "Therapy session",
        "sections": _shareable_sections(buckets, resolved, themes),
        "findings": [],
        "sourceReferences": [{"type": "capture", "captureId": str(capture.id)} for capture in captures],
        "therapyFormat": resolved,
    }


def _session_so_far(buckets: dict[str, list[str]], fmt: str, themes: list[dict[str, Any]], note_count: int, audio_count: int) -> dict[str, Any]:
    primary = buckets.get(_PRIMARY_SECTION[fmt], [])
    narrative = " ".join(primary[:3]) if primary else "Nothing captured yet — add a note when you're ready."
    bits: list[str] = []
    if note_count:
        bits.append(f"{note_count} note{'s' if note_count != 1 else ''}")
    if audio_count:
        bits.append(f"{audio_count} audio recap{'s' if audio_count != 1 else ''}")
    captured = " · ".join(bits) if bits else "no captures yet"
    theme_text = ", ".join(theme["label"] for theme in themes)
    line = f"Captured: {captured}" + (f" · themes: {theme_text}" if theme_text else "")
    # Thread coverage (live agenda): v1 derives "threads" from detected themes and marks them covered
    # because they were captured this session. Brief-driven threads slot in here once briefs ship.
    thread_coverage = [{"label": theme["label"], "covered": True} for theme in themes]
    return {"line": line, "narrative": narrative, "threadCoverage": thread_coverage}


def build_therapy_synthesis(session: Session, captures: list[Capture], *, generated_at: str) -> dict[str, Any]:
    """Build the full ``therapy`` metadata block: two planes, session-so-far, themes, risk, release."""
    metadata = session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {}
    fmt = therapy_format_from_session(session)
    note_count = sum(1 for capture in captures if capture.capture_type == CaptureType.note)
    audio_count = sum(1 for capture in captures if capture.capture_type == CaptureType.audio)
    photo_count = sum(1 for capture in captures if capture.capture_type == CaptureType.photo)
    texts = [text for text in (_capture_text(capture) for capture in captures) if text]
    buckets = _section_bodies(captures, fmt)
    themes = _detect_themes(texts)

    shareable_sections = _shareable_sections(buckets, fmt, themes)
    shareable_view = [
        {"id": section["id"], "title": section["title"], "body": " ".join(block["text"] for block in section["blocks"])}
        for section in shareable_sections
    ]

    audio_transcripts = [
        {"captureId": str(capture.id), "text": _capture_text(capture)}
        for capture in captures
        if capture.capture_type == CaptureType.audio and _capture_text(capture)
    ]
    reflections = metadata.get("therapy_reflections")
    private_plane = {
        "reflections": reflections.strip() if isinstance(reflections, str) and reflections.strip() else None,
        "audioTranscripts": audio_transcripts,
    }

    # Risk: assisted suggestion vs. clinician-confirmed (never auto-set). The confirmed flag is owned
    # by the clinician via the risk endpoint and stored as `therapy_risk` input.
    confirmed_risk = metadata.get("therapy_risk") if isinstance(metadata.get("therapy_risk"), dict) else {}
    suggested_cue = _detect_risk_cue(texts)
    risk = {
        "active": bool(confirmed_risk.get("active")),
        "level": confirmed_risk.get("level"),
        "note": confirmed_risk.get("note"),
        "confirmedAt": confirmed_risk.get("confirmedAt"),
        "confirmedBy": confirmed_risk.get("confirmedBy"),
        "suggested": suggested_cue is not None and not confirmed_risk.get("active"),
        "cue": suggested_cue,
    }

    release_input = metadata.get("therapy_release") if isinstance(metadata.get("therapy_release"), dict) else {}
    release = {
        "released": bool(release_input.get("released")),
        "releasedAt": release_input.get("releasedAt"),
    }

    return {
        "schemaVersion": THERAPY_SYNTHESIS_VERSION,
        "format": fmt,
        "availableFormats": list(THERAPY_REPORT_FORMATS),
        "sessionSoFar": _session_so_far(buckets, fmt, themes, note_count, audio_count),
        "themes": themes,
        "risk": risk,
        "release": release,
        "planes": {
            "shareable": {"format": fmt, "sections": shareable_view},
            "private": private_plane,
        },
        "noteCount": note_count,
        "audioCount": audio_count,
        "photoCount": photo_count,
        "generatedAt": generated_at,
    }


def apply_therapy_synthesis(
    session: Session,
    captures: list[Capture],
    *,
    db: Any,
    generated_at: str,
) -> None:
    """Write the therapy synthesis onto the session (shareable report + therapy metadata block).

    Mirrors the aesthetics ``regenerate_session_report`` contract: sets ``report_model`` /
    ``generated_report`` (shareable plane only), the ``therapy`` metadata block, summary, status,
    and clears the stale flag — so ``session_is_complete`` and the live report behave identically.
    """
    from app.services.reporting import render_report_body_markdown

    fmt = therapy_format_from_session(session)
    report_model = build_therapy_report_model(session, captures, fmt=fmt)
    synthesis = build_therapy_synthesis(session, captures, generated_at=generated_at)

    session.report_model = report_model
    session.report_template_key = session.report_template_key or get_report_template(session.report_template_key).key
    session.generated_report = render_report_body_markdown(report_model, db=db, session=session)
    session.generated_summary = synthesis["sessionSoFar"]["line"]
    session.summary = synthesis["sessionSoFar"]["line"]
    session.organization_source = OrganizationSource.ai_engine

    metadata = session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {}
    session.extracted_metadata = {
        **metadata,
        "therapy": synthesis,
        "generated_output_stale": False,
        "generated_at": generated_at,
    }
    session.status = SessionStatus.needs_review if session.patient_id else SessionStatus.unassigned


def set_therapy_format(session: Session, fmt: str) -> None:
    """Persist the therapist's chosen shareable-plane format (re-projected on next synthesis)."""
    metadata = session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {}
    session.extracted_metadata = {**metadata, "therapy_format": normalize_therapy_format(fmt)}


def set_therapy_release(session: Session, *, released: bool, released_at: str | None) -> None:
    """Record the explicit Release-to-client act on the shareable plane (never auto-released)."""
    metadata = session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {}
    session.extracted_metadata = {
        **metadata,
        "therapy_release": {"released": bool(released), "releasedAt": released_at if released else None},
    }


def set_therapy_risk(
    session: Session,
    *,
    active: bool,
    level: str | None,
    note: str | None,
    confirmed_by: str | None,
    confirmed_at: str | None,
) -> None:
    """Record a clinician-confirmed, dated risk flag (assisted detection only suggests — §C3)."""
    metadata = session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {}
    session.extracted_metadata = {
        **metadata,
        "therapy_risk": {
            "active": bool(active),
            "level": level if active else None,
            "note": note if active else None,
            "confirmedBy": confirmed_by if active else None,
            "confirmedAt": confirmed_at if active else None,
        },
    }


def therapy_reflections_set(session: Session, reflections: str | None) -> None:
    """Persist the private-plane reflections text (therapist-only; never exported)."""
    metadata = session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {}
    cleaned = reflections.strip() if isinstance(reflections, str) and reflections.strip() else None
    session.extracted_metadata = {**metadata, "therapy_reflections": cleaned}


# --- Route-facing orchestrators (thin services; routes stay thin) ---------------------------------


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_therapy_session(db: DbSession, principal: CurrentPrincipal, session_id: str) -> Session:
    """Load a tenant-scoped session and assert this is a therapy tenant."""
    from app.services.caseload import tenant_vertical
    from app.services.capture_storage import get_session_for_tenant
    from app.services.sessions import parse_uuid

    if tenant_vertical(db, principal.tenant_id) != "therapy":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Therapy actions require a therapy tenant")
    return get_session_for_tenant(db, principal.tenant_id, parse_uuid(session_id, "session_id"))


def _resynthesize_and_payload(db: DbSession, principal: CurrentPrincipal, session: Session, *, action: str, details: dict[str, Any]) -> dict[str, Any]:
    """Persist the mutated input, re-run the deterministic synthesis when idle, and return the session."""
    from app.auth.service import audit
    from app.services.ai_jobs import regenerate_session_report_if_idle
    from app.services.capture_storage import session_payload

    db.flush()
    audit(db, tenant_id=principal.tenant_id, actor_user_id=principal.user_id, action=action, target_type="session", target_id=session.id, details=details)
    db.commit()
    # Recompute the therapy block from the new input (no-op while captures are still processing — it
    # then refreshes once the capture chain drains, like the aesthetics live report).
    regenerate_session_report_if_idle(db, tenant_id=principal.tenant_id, session_id=session.id, created_by_user_id=principal.user_id, force=True)
    db.refresh(session)
    return session_payload(session, db)


def update_therapy_format(db: DbSession, principal: CurrentPrincipal, session_id: str, fmt: str) -> dict[str, Any]:
    """Switch the shareable-plane note format (DAP/SOAP/BIRP); re-projects the same content."""
    session = _load_therapy_session(db, principal, session_id)
    resolved = normalize_therapy_format(fmt)
    set_therapy_format(session, resolved)
    return _resynthesize_and_payload(db, principal, session, action="therapy.set_format", details={"format": resolved})


def update_therapy_release(db: DbSession, principal: CurrentPrincipal, session_id: str, released: bool) -> dict[str, Any]:
    """Explicitly release (or withdraw) the shareable summary to the client — a deliberate act."""
    session = _load_therapy_session(db, principal, session_id)
    set_therapy_release(session, released=released, released_at=_utc_now_iso() if released else None)
    return _resynthesize_and_payload(db, principal, session, action="therapy.release", details={"released": released})


def update_therapy_risk(
    db: DbSession,
    principal: CurrentPrincipal,
    session_id: str,
    *,
    active: bool,
    level: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Clinician-confirm (or clear) a dated risk flag. Assisted detection only suggests — never auto-sets."""
    session = _load_therapy_session(db, principal, session_id)
    confirmer = principal.user.full_name or principal.user.email
    set_therapy_risk(
        session,
        active=active,
        level=level,
        note=note,
        confirmed_by=confirmer,
        confirmed_at=_utc_now_iso() if active else None,
    )
    return _resynthesize_and_payload(db, principal, session, action="therapy.risk", details={"active": active, "level": level})


def update_therapy_reflections(db: DbSession, principal: CurrentPrincipal, session_id: str, reflections: str | None) -> dict[str, Any]:
    """Save the private-plane reflections (therapist-only; never exported)."""
    session = _load_therapy_session(db, principal, session_id)
    therapy_reflections_set(session, reflections)
    return _resynthesize_and_payload(db, principal, session, action="therapy.reflections", details={})
