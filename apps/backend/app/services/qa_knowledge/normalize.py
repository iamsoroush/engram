"""Orthography-folding + tokenization + language detection for Q&A knowledge retrieval.

The lexical half of retrieval must match on the clinical FACT, not the exact bytes: Persian output
varies cosmetically (Arabic vs Persian letter forms, ZWNJ vs space, Persian vs Latin digits) while the
question is "the same". These helpers fold those differences into a stable ``search_text`` used both
when a row is indexed and when a query is matched — mirroring the eval harness's tolerant matcher so
the two stay in step. Pure functions (no DB / no gateway) so ranking is deterministic and unit-tested.
"""
from __future__ import annotations

import re

# Fold Arabic presentation/letter forms to their Persian equivalents (same as the eval `canon`).
_ARABIC_TO_PERSIAN = str.maketrans({"ي": "ی", "ك": "ک", "ﻪ": "ه", "ة": "ه", "ﻱ": "ی"})
# Persian + Arabic-Indic digits → ASCII, so «۲۰» and "20" compare equal.
_DIGITS_TO_LATIN = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_ZWNJ = "‌"

_WORD_RE = re.compile(r"[0-9A-Za-z؀-ۿ]+")
_PERSIAN_RE = re.compile(r"[؀-ۿ]")
_LATIN_RE = re.compile(r"[A-Za-z]")

# Very common Persian + English function words carry no retrieval signal; dropping them keeps the
# token-overlap score about clinical content, not glue. Deliberately small (recall-safe).
_STOPWORDS = frozenset(
    {
        # English
        "the", "a", "an", "is", "are", "am", "to", "of", "for", "and", "or", "in", "on", "it",
        "my", "me", "i", "you", "your", "can", "do", "does", "did", "be", "was", "were", "this",
        "that", "with", "at", "as", "if", "so", "we", "us", "our",
        # Persian
        "و", "در", "به", "از", "که", "را", "با", "این", "آن", "است", "هست", "برای", "یک", "یه",
        "می", "من", "تو", "شما", "ما", "آیا", "هم", "یا", "تا",
    }
)


def canonicalize(text: object) -> str:
    """Fold digits + Persian forms, strip ZWNJ, collapse whitespace, lowercase — the match form."""
    value = str(text or "").translate(_DIGITS_TO_LATIN).translate(_ARABIC_TO_PERSIAN)
    return re.sub(r"\s+", " ", value.replace(_ZWNJ, "")).strip().lower()


def tokens(text: object, *, drop_stopwords: bool = True) -> list[str]:
    """The content tokens of ``text`` under canonicalization (stopwords dropped by default)."""
    canonical = canonicalize(text)
    found = _WORD_RE.findall(canonical)
    if not drop_stopwords:
        return found
    return [token for token in found if token not in _STOPWORDS]


def token_set(text: object) -> set[str]:
    """The set of content tokens (for overlap scoring)."""
    return set(tokens(text))


def build_search_text(*, title: str | None = None, question: str | None, answer: str | None) -> str:
    """The stored lexical target for an exemplar: canonicalized title + question + answer.

    Title matters: a clinic often labels a template by its topic («ورزش بعد از بوتاکس») and leaves
    the question pattern blank, so a query «کی میتونم ورزش کنم؟» must still match on the topic word in
    the title. Omitting the title (the pre-AES-1902 behaviour) silently dropped that grounding signal.
    """
    return canonicalize(f"{title or ''} {question or ''} {answer or ''}")


# Question-word markers (fa + en) that make a bare title read as a question pattern. Used to migrate
# the owner's trap (AES-1902): question-shaped text typed into the optional `title` while `question`
# stayed empty, so retrieval never learned it was the question. Kept small + recall-safe.
_QUESTION_WORDS = frozenset(
    {
        # Persian
        "کی", "کِی", "چی", "چه", "چرا", "کجا", "چطور", "چگونه", "چند", "چقدر", "آیا", "کدام", "چند وقت",
        # English
        "what", "when", "why", "where", "how", "which", "who", "whom", "can", "could", "should",
        "will", "would", "do", "does", "is", "are", "am",
    }
)


def looks_like_question(text: object) -> bool:
    """Whether a title reads as a question — ends with ?/؟ or opens on a question word.

    Deliberately lenient (recall-safe): the cost of a false positive here is copying a topic label into
    ``question`` (harmless — search_text folds both), while a miss leaves the owner's mis-entry
    ungrounded. Pure + unit-tested so the migration and any UI guard stay in step.
    """
    folded = canonicalize(text)
    if not folded:
        return False
    if folded.endswith("?") or folded.endswith("؟"):
        return True
    return any(token in _QUESTION_WORDS for token in tokens(text, drop_stopwords=False))


def detect_language(text: object) -> str:
    """Cheap fa/en/und language tag from script counts (Persian script vs Latin).

    Deterministic and dependency-free — good enough to bias same-language retrieval and to stamp a
    stored exemplar; not a full language identifier.
    """
    value = str(text or "")
    persian = len(_PERSIAN_RE.findall(value))
    latin = len(_LATIN_RE.findall(value))
    if persian == 0 and latin == 0:
        return "und"
    return "fa" if persian >= latin else "en"
