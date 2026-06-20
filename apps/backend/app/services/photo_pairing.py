"""Deterministic before/after photo pairing from caption pairing attributes (no LLM).

The photo-caption job (Job 2) emits per-photo pairing *attributes*
(``{region, laterality, view, phase, isProductLabel}``). Turning those attributes into actual
before/after pairs is a **deterministic backend step**, not an LLM job: photos of the same
region+laterality+view are matched across phases. The result is stored on each photo capture's
metadata (``photo_pairing``) so downstream surfaces (the report's before/after rendering — a
separate track) can render pairs without re-deriving them. Product-label shots and photos without a
region are left unpaired.
"""
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.models import Capture, CaptureStatus, CaptureType, Session

__all__ = ["caption_pairing_attributes", "compute_photo_pairs", "recompute_session_photo_pairing"]


def caption_pairing_attributes(capture: Capture) -> dict[str, Any] | None:
    """Return the pairing attributes the caption job stored on a photo capture, or None."""
    metadata = capture.capture_metadata if isinstance(capture.capture_metadata, dict) else {}
    caption = metadata.get("caption")
    pairing = caption.get("pairing") if isinstance(caption, dict) else None
    return pairing if isinstance(pairing, dict) else None


def _pair_key(attrs: dict[str, Any]) -> str | None:
    """Stable grouping key for a photo's anatomical site, or None when there's no region to pair on."""
    region = str(attrs.get("region") or "").strip().lower()
    if not region:
        return None
    laterality = str(attrs.get("laterality") or "").strip().lower()
    view = str(attrs.get("view") or "").strip().lower()
    return f"{region}|{laterality}|{view}"


def _single(pair_key: str | None) -> dict[str, Any]:
    return {"role": "single", "pairKey": pair_key, "pairedCaptureId": None}


def compute_photo_pairs(photos: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Pair before↔after photos deterministically from their pairing attributes.

    ``photos`` is an ordered-by-capture-time list of ``{"captureId": str, "pairing": {...}}``. Photos
    are grouped by (region, laterality, view); within a group an explicit ``before`` is matched to the
    next explicit ``after``, and a clean group of exactly two phase-less photos is paired in capture
    order. Product-label shots and region-less photos stay unpaired. Returns
    ``{captureId: {role, pairKey, pairedCaptureId}}`` for every input photo.
    """
    result: dict[str, dict[str, Any]] = {}
    groups: dict[str, list[dict[str, Any]]] = {}
    for photo in photos:
        capture_id = str(photo.get("captureId"))
        attrs = photo.get("pairing") if isinstance(photo.get("pairing"), dict) else {}
        if attrs.get("isProductLabel") is True:
            result[capture_id] = {"role": "product-label", "pairKey": None, "pairedCaptureId": None}
            continue
        key = _pair_key(attrs)
        if key is None:
            result[capture_id] = _single(None)
            continue
        groups.setdefault(key, []).append({"captureId": capture_id, "phase": attrs.get("phase")})

    for key, members in groups.items():
        befores = [m for m in members if m["phase"] == "before"]
        afters = [m for m in members if m["phase"] == "after"]
        paired: set[str] = set()
        for before, after in zip(befores, afters):
            result[before["captureId"]] = {"role": "before", "pairKey": key, "pairedCaptureId": after["captureId"]}
            result[after["captureId"]] = {"role": "after", "pairKey": key, "pairedCaptureId": before["captureId"]}
            paired.add(before["captureId"])
            paired.add(after["captureId"])
        leftovers = [m for m in members if m["captureId"] not in paired]
        unphased = [m for m in leftovers if m["phase"] not in ("before", "after", "during")]
        if len(leftovers) == 2 and len(unphased) == 2:
            first, second = leftovers  # capture-order: earlier is the "before"
            result[first["captureId"]] = {"role": "before", "pairKey": key, "pairedCaptureId": second["captureId"]}
            result[second["captureId"]] = {"role": "after", "pairKey": key, "pairedCaptureId": first["captureId"]}
        else:
            for member in leftovers:
                phase = member["phase"]
                role = phase if phase in ("before", "after", "during") else "single"
                result[member["captureId"]] = {"role": role, "pairKey": key, "pairedCaptureId": None}
    return result


def recompute_session_photo_pairing(db: DbSession, *, session: Session) -> None:
    """Recompute + persist deterministic photo pairing for a session's captioned photos (idempotent).

    Only photos carrying caption pairing attributes participate (Basic / un-captioned photos are
    skipped). Writes each photo's ``photo_pairing`` block; the caller commits.
    """
    photos = list(
        db.execute(
            select(Capture)
            .where(
                Capture.tenant_id == session.tenant_id,
                Capture.session_id == session.id,
                Capture.capture_type == CaptureType.photo,
                Capture.status != CaptureStatus.deleted,
            )
            .order_by(Capture.captured_at, Capture.created_at)
        ).scalars()
    )
    captioned = [(capture, caption_pairing_attributes(capture)) for capture in photos]
    captioned = [(capture, attrs) for capture, attrs in captioned if attrs is not None]
    if not captioned:
        return
    pairs = compute_photo_pairs([{"captureId": str(capture.id), "pairing": attrs} for capture, attrs in captioned])
    for capture, _ in captioned:
        pairing_result = pairs.get(str(capture.id))
        if pairing_result is None:
            continue
        metadata = dict(capture.capture_metadata or {})
        if metadata.get("photo_pairing") != pairing_result:
            metadata["photo_pairing"] = pairing_result
            capture.capture_metadata = metadata
