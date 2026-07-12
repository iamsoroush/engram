"""Deterministic red-flag classification for incoming patient Q&A (AES-1901).

An aesthetics patient can report an emergency between visits — the classic being a filler
vascular occlusion (skin blanching + severe pain + vision change; see the eval's QD-05). Those
questions must not sit in the inbox looking like any other "is the swelling normal?". At ingest we
scan the question against a small, sensitivity-biased lexicon (both fa + en) and mark a hit as
**urgent** so the inbox row, the top-bar badge, and the attention bell all escalate and an in-app
toast fires.

Deliberately deterministic (no LLM, no gateway): it must run on the public ``/ask`` path even
gateway-less, and never be the thing that's "down". It errs toward **sensitivity** — a false-positive
urgent costs a doctor one extra glance; a missed vascular occlusion costs tissue. An LLM escalation
flag from the ``qa_draft`` output is a registered, eval-gated fast-follow (AES-1904), not this.

Category keys are stable identifiers the frontend localizes (``qa.redflag.<key>``) — so the toast
reads «سؤال فوری بیمار — تاری دید» in fa and "Urgent patient question — vision changes" in en.
Pure functions (reuse ``normalize`` folding) so classification is unit-tested and reproducible.
"""
from __future__ import annotations

from app.services.qa_knowledge import normalize

# Each category → (single-word trigger tokens, multi-word trigger phrases). Tokens match the folded
# token SET (so «تار» hits but a longer word containing it does not); phrases match as a folded
# substring (so «تاری دید» / "shortness of breath" hit as written). Order = toast-label priority
# (the most time-critical first): a filler occlusion surfaces as "vision changes".
_LEXICON: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = [
    (
        "vision",
        ("تاری", "تار", "دوبینی", "کوری", "نمیبینم", "نمی‌بینم", "blurry", "blurred", "blindness", "blind"),
        ("تاری دید", "تار میبینم", "تار می‌بینم", "دید تار", "کاهش دید", "vision change", "vision changes",
         "changes in vision", "losing vision", "can't see", "cannot see", "double vision", "blurry vision"),
    ),
    (
        "necrosis",
        ("بلانچ", "بلانچینگ", "نکروز", "کبودی", "کبود", "بنفش", "blanching", "blanch", "necrosis", "dusky",
         "mottled", "mottling"),
        ("سفید شده", "سفید شد", "سفید شدن", "رنگ پریده", "لکه سفید", "پوست سفید", "سیاه شدن", "white patch",
         "white patches", "pale skin", "skin turning white", "turning white", "purple patch", "skin going black"),
    ),
    (
        "breathing",
        ("خفگی", "wheezing", "wheeze"),
        ("تنگی نفس", "نفس تنگ", "نفسم بالا نمیاد", "نمیتونم نفس بکشم", "نمی‌تونم نفس بکشم",
         "shortness of breath", "short of breath", "can't breathe", "cannot breathe", "trouble breathing",
         "hard to breathe", "difficulty breathing", "choking"),
    ),
    (
        "severe_pain",
        ("unbearable",),
        ("درد شدید", "درد زیاد", "خیلی درد", "درد وحشتناک", "درد غیرقابل تحمل", "درد پخش", "پخش شدن درد",
         "درد داره بیشتر میشه", "severe pain", "spreading pain", "pain spreading", "worsening pain",
         "unbearable pain", "excruciating", "intense pain", "getting much worse"),
    ),
    (
        "fever",
        ("تب", "لرز", "fever", "chills", "feverish"),
        ("high temperature", "تب کردم", "تب دارم"),
    ),
]

# Every category key, in label-priority order (stable; the frontend renders `qa.redflag.<key>`).
RED_FLAG_CATEGORIES: tuple[str, ...] = tuple(key for key, _, _ in _LEXICON)


def classify_urgency(text: str | None) -> list[str]:
    """The red-flag categories a question hits, in label-priority order ([] when none).

    Sensitivity-biased: a single token or phrase anywhere in the (orthography-folded) question is a
    hit. The first category is the one whose localized label drives the urgent toast.
    """
    folded = normalize.canonicalize(text)
    if not folded:
        return []
    token_set = set(normalize.tokens(text, drop_stopwords=False))
    hits: list[str] = []
    for key, tokens_, phrases in _LEXICON:
        matched = any(token in token_set for token in (normalize.canonicalize(t) for t in tokens_))
        if not matched:
            matched = any(normalize.canonicalize(phrase) in folded for phrase in phrases)
        if matched:
            hits.append(key)
    return hits


def is_urgent(text: str | None) -> bool:
    """Whether the question trips any red flag (the ingest gate for marking a thread urgent)."""
    return bool(classify_urgency(text))
