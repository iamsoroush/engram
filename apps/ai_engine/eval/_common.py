#!/usr/bin/env python3
"""Shared two-tier eval harness — matchers, LLM judge, fixture store (used by every *_eval.py).

The eval epic scores each AI job on two tiers (see ``docs/ai_engine/eval-epic.md``):

* **Safety gates** — deterministic matchers. HARD pass/fail; a failure blocks ship and exits non-zero.
* **Quality** — an LLM-as-judge rubric scored 0..1. Advisory by default (tracked to drive iteration);
  ``EVAL_STRICT_QUALITY=1`` promotes below-threshold quality (and judge-smoke misses) to blocking.

This module factors out what every eval shares: tolerant Persian/Farsi-aware matching primitives, the
gateway judge call + parsing, and a fixture store that reads media + sibling ``.json`` from a directory
(``EVAL_FIXTURES_DIR`` when set — kept OUTSIDE the repo so capture media is never committed; otherwise
the in-repo ``eval/fixtures/<job>/`` which is gitignored except ``.gitkeep``). Each ``*_eval.py`` keeps
its own job-specific gate function + judge rubric + scenario cases and composes them from these.
"""
from __future__ import annotations

import datetime
import json
import os
import pathlib
import re
import subprocess
from typing import Any

from ai_engine.processing import (  # noqa: E402
    gateway_client,
    normalize_digits_to_latin,
    transcription_is_configured,
)

# --- Config -------------------------------------------------------------------------------------

DEFAULT_MIN_SCORE = 0.7
STRICT_QUALITY = os.environ.get("EVAL_STRICT_QUALITY", "").strip() not in ("", "0", "false", "False")
# The judge grades on a capable model chosen for grading, INDEPENDENT of whichever model is under test
# so the grader doesn't drift when a job's model is swapped. Eval-only config (not production config.py).
JUDGE_MODEL = os.environ.get("EVAL_JUDGE_MODEL", "").strip() or "gpt-5.4-mini"

AUDIO_SUFFIXES = {".m4a", ".mp3", ".wav", ".flac", ".ogg", ".aac", ".opus", ".webm", ".mp4"}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".bmp", ".gif"}
MIME_BY_SUFFIX = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp",
    ".heic": "image/heic", ".heif": "image/heif", ".bmp": "image/bmp", ".gif": "image/gif",
}

try:
    HERE = pathlib.Path(__file__).resolve().parent
except NameError:  # piped via stdin
    HERE = pathlib.Path("/app/eval")


def gateway_configured() -> bool:
    """Whether a real AI gateway is configured (evals SKIP the gateway tier without one)."""
    return transcription_is_configured()


# --- Tolerant matching primitives ---------------------------------------------------------------
#
# The model's Persian output varies cosmetically (Arabic vs Persian letter forms, ZWNJ vs space,
# Persian vs Latin digits) while the clinical fact is identical, so naïve ==/in gives false failures.
# These fold those differences before comparing — the clinical fact must hold, not the exact bytes.

LATIN_WORD_RE = re.compile(r"[A-Za-z]{2,}")
NUMBER_TOKEN_RE = re.compile(r"\d+(?:\.\d+)?")
_ARABIC_TO_PERSIAN = str.maketrans({"ي": "ی", "ك": "ک", "ﻪ": "ه", "ة": "ه", "ﻱ": "ی"})

# High-precision diagnostic tells a NEUTRAL caption must never contain — mirrors the captioner prompt's
# explicit prohibitions ("Do NOT diagnose, assess severity, judge outcomes, or state what is absent or
# normal; never write 'no signs of …'"). The fuzzy call is left to the objectiveNotDiagnostic judge dim.
DIAGNOSTIC_TELLS = [
    # English
    "no sign", "no signs of", "no evidence of", "without sign", "unremarkable", "normal", "abnormal",
    "healthy", "mild", "moderate", "severe", "improv", "worsen", "resolved", "diagnos",
    "consistent with", "suggestive of", "infection", "infected", "benign", "malignant",
    # Persian
    "بدون علائم", "بدون نشانه", "هیچ نشانه", "دیده نمی‌شود", "طبیعی", "نرمال", "غیرطبیعی", "سالم",
    "خفیف", "متوسط", "شدید", "بهبود", "بدتر", "تشخیص", "عفونت", "خوش‌خیم", "بدخیم", "بدون عارضه",
]


def canon(text: Any) -> str:
    """Canonicalize for tolerant substring matching: Latin digits, Persian forms, no ZWNJ/extra space."""
    value = normalize_digits_to_latin(str(text or "")).translate(_ARABIC_TO_PERSIAN)
    return re.sub(r"\s+", " ", value.replace("‌", "")).strip().lower()


def loose(text: Any) -> str:
    """Even more tolerant: also drop spaces, so «سی‌سی» / «سی سی» / «سیسی» all compare equal."""
    return canon(text).replace(" ", "")


def contains(haystack: str, needle: Any) -> bool:
    """True if ``needle`` appears in ``haystack`` under either canonical or space-insensitive folding."""
    return canon(needle) in canon(haystack) or loose(needle) in loose(haystack)


def number_tokens(text: str) -> set[str]:
    """The set of numeric tokens in ``text`` (digits normalized to Latin), for exact dose matching."""
    return set(NUMBER_TOKEN_RE.findall(normalize_digits_to_latin(str(text))))


def latin_offenders(text: str, *, allow: Any = ()) -> list[str]:
    """Latin-script words in ``text`` that aren't whitelisted (anti-romanization gate).

    ``allow`` is any iterable of permitted Latin tokens (brand names, lot codes). The regex splits an
    alphanumeric lot like "ABC123" into "ABC", so an offender that is a FRAGMENT of a whitelisted token
    is allowed too — pass the expected lot/brand strings and you needn't enumerate fragments.
    """
    allowed = {str(token).lower() for token in allow}
    return [
        word for word in LATIN_WORD_RE.findall(str(text))
        if word.lower() not in allowed and not any(word.lower() in token for token in allowed)
    ]


def diagnostic_tells_in(text: str) -> list[str]:
    """The high-precision diagnostic tells present in ``text`` (empty == stays objective)."""
    return [tell for tell in DIAGNOSTIC_TELLS if contains(text, tell)]


# --- Quality tier: LLM-as-judge -----------------------------------------------------------------


def build_judge_prompt(
    *,
    role: str,
    rubric: dict[str, str],
    dimensions: list[str],
    reference: str,
    candidate: str,
    reference_label: str = "REFERENCE (ground truth)",
    candidate_label: str = "CANDIDATE (to score)",
    reference_optional: bool = False,
) -> str:
    """Assemble a judge prompt: role + per-dimension rubric + reference/candidate + strict-JSON shape."""
    lines = "\n".join(f"- {dim}: {rubric[dim]}" for dim in dimensions if dim in rubric)
    keys = ", ".join(f'"{dim}": 0.0' for dim in dimensions if dim in rubric)
    if reference:
        reference_block = f"{reference_label}:\n{reference}\n\n"
    elif reference_optional:
        reference_block = (
            f"{reference_label}: (none provided — score reference-free dimensions from the candidate "
            "alone; for reference-dependent dimensions assume the candidate's factual claims are correct.)\n\n"
        )
    else:
        reference_block = f"{reference_label}: (none)\n\n"
    return (
        f"{role}\nScore ONLY the requested dimensions, each from 0.0 to 1.0.\n\n"
        f"Dimensions:\n{lines}\n\n"
        f"{reference_block}"
        f"{candidate_label}:\n{candidate}\n\n"
        "Return STRICT JSON only, no markdown, exactly this shape:\n"
        f'{{"scores": {{{keys}}}, "rationale": "one short sentence"}}'
    )


def parse_judge(raw_text: str, dimensions: list[str]) -> dict[str, Any]:
    """Parse the judge's strict-JSON scores; clamp to [0,1]; ``ok=False`` when unparseable."""
    text = (raw_text or "").strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {"scores": {}, "rationale": "judge returned non-JSON", "ok": False}
    raw_scores = parsed.get("scores") if isinstance(parsed.get("scores"), dict) else {}
    scores: dict[str, float] = {}
    for dim in dimensions:
        value = raw_scores.get(dim)
        scores[dim] = max(0.0, min(float(value), 1.0)) if isinstance(value, int | float) and not isinstance(value, bool) else 0.0
    return {"scores": scores, "rationale": str(parsed.get("rationale") or "").strip(), "ok": True}


def judge(
    *,
    role: str,
    rubric: dict[str, str],
    dimensions: list[str],
    reference: str,
    candidate: str,
    task: str = "report_synthesis",
    **prompt_kwargs: Any,
) -> dict[str, Any]:
    """Run the LLM judge on the gateway; return ``{scores: {dim: 0..1}, rationale, ok}``.

    ``task`` only selects the gateway base_url/key (all fall back to the transcription gateway); the
    model is always ``JUDGE_MODEL``. Network/parse failure → ``ok=False`` so callers can degrade to
    "judge unavailable" instead of scoring it as a quality failure.
    """
    prompt = build_judge_prompt(
        role=role, rubric=rubric, dimensions=dimensions, reference=reference, candidate=candidate, **prompt_kwargs
    )
    client = gateway_client(task)
    response = client.chat.completions.create(
        model=JUDGE_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    return parse_judge(response.choices[0].message.content or "", dimensions)


def min_score(scores: dict[str, float]) -> float:
    """The weakest dimension — used to gate quality (one bad dimension must sink the verdict)."""
    return min(scores.values()) if scores else 0.0


def quality_line(scores: dict[str, float], threshold: float) -> str:
    """Render per-dimension scores, marking any below the threshold with a ↓."""
    return ", ".join(f"{dim}={value:.2f}{'' if value >= threshold else '↓'}" for dim, value in scores.items())


# --- Fixture store --------------------------------------------------------------------------------


def fixtures_dir(job: str) -> pathlib.Path:
    """Resolve the fixtures dir for a job.

    ``EVAL_FIXTURES_DIR`` (when set) points at a location OUTSIDE the repo — capture media live there
    (or are pulled there from object storage), never committed. Otherwise the in-repo
    ``eval/fixtures/<job>/`` (gitignored except ``.gitkeep``) is used.
    """
    override = os.environ.get("EVAL_FIXTURES_DIR", "").strip()
    base = pathlib.Path(override) if override else (HERE / "fixtures")
    return base / job


def load_fixtures(job: str, suffixes: set[str]) -> list[dict[str, Any]]:
    """Discover ``<dir>/<case>.<media>`` + sibling ``<case>.json`` for a job.

    Returns a list of ``{name, media: Path, spec: dict|None, error?: str}``; ``spec`` is None when the
    sibling ``.json`` is missing or unparseable (the caller reports it as a skip).
    """
    directory = fixtures_dir(job)
    if not directory.is_dir():
        return []
    fixtures: list[dict[str, Any]] = []
    for media in sorted(directory.iterdir()):
        if media.suffix.lower() not in suffixes:
            continue
        spec_path = media.with_suffix(".json")
        if not spec_path.exists():
            fixtures.append({"name": media.name, "media": media, "spec": None})
            continue
        try:
            fixtures.append({"name": media.name, "media": media, "spec": json.loads(spec_path.read_text(encoding="utf-8"))})
        except (json.JSONDecodeError, OSError) as exc:
            fixtures.append({"name": media.name, "media": media, "spec": None, "error": str(exc)})
    return fixtures


# --- Exit-code policy ----------------------------------------------------------------------------


def exit_code(*, self_tests_ok: bool, safety_fail: int, quality_fail: int = 0, judge_smoke_ok: bool = True) -> int:
    """The suite's pass/fail contract: SAFETY blocks; quality is advisory unless EVAL_STRICT_QUALITY=1."""
    blocking_failed = (not self_tests_ok) or safety_fail > 0
    if STRICT_QUALITY:
        blocking_failed = blocking_failed or quality_fail > 0 or not judge_smoke_ok
    return 1 if blocking_failed else 0


# --- Machine-readable scorecard -------------------------------------------------------------------
#
# Each ``*_eval.py`` calls ``write_scorecard`` once at the end of ``main()``; ``run_all.py`` merges the
# per-module files into ``eval/out/scorecard.json``. The schema is deliberately FLAT metrics + tags so a
# scorecard imports cleanly into an experiment tracker (MLflow-class) later: top-level tags (module,
# git_sha, models_under_test, judge_model, gateway, timestamp), a flat numeric ``metrics`` block (one
# scalar per key — the trendable series), and a per-case ``cases`` list for drill-down.

OUT_DIR = HERE / "out"


def _git_sha() -> str:
    """Best-effort short commit sha for tagging a scorecard (CI env first, then git, then ``unknown``)."""
    for env_key in ("GITHUB_SHA", "GIT_SHA"):
        sha = os.environ.get(env_key, "").strip()
        if sha:
            return sha[:12]
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=str(HERE), timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return "unknown"


def env_models(*env_keys: str) -> list[str]:
    """The non-empty ``AI_ENGINE_*_MODEL`` values among ``env_keys``, de-duplicated — a scorecard tag
    recording which model(s) produced a run, so a swap is visible as a step in the time series."""
    models: list[str] = []
    for key in env_keys:
        value = os.environ.get(key, "").strip()
        if value and value not in models:
            models.append(value)
    return models


def env_reasoning_effort() -> str | None:
    """The configured synthesis reasoning effort, if any (a scorecard run-config tag). None when unset.

    GPT-5-class models take a ``reasoning_effort`` quality knob instead of temperature; recording it
    next to the model makes an effort change visible in the trend the same way a model swap is.
    """
    value = os.environ.get("AI_ENGINE_REPORT_SYNTHESIS_REASONING_EFFORT", "").strip()
    return value or None


def capture_prompt_version(output: Any) -> str | None:
    """Best-effort read of a job output's prompt-version stamp — ``None`` when absent, never raises.

    The AI jobs are gaining a ``promptVersion`` (a.k.a. ``prompt_version``) field in their output
    envelope so a prompt change is attributable in the trend. This reader is deliberately TOLERANT: a
    missing field, a non-dict output, or ``None`` all yield ``None`` (no failure) — so the scorecard
    captures the version the moment jobs start emitting it, with zero coupling before then.
    """
    if not isinstance(output, dict):
        return None
    value = output.get("promptVersion")
    if value is None:
        value = output.get("prompt_version")
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        text = str(value).strip()
        return text or None
    return None


def write_scorecard(
    module: str,
    *,
    metrics: dict[str, Any],
    cases: list[dict[str, Any]] | None = None,
    models_under_test: list[str] | None = None,
    prompt_version: str | None = None,
) -> pathlib.Path:
    """Emit this module's scorecard to ``eval/out/<module>.json`` and return the path.

    Args:
        module: the module's short name (e.g. ``"treatments_eval"``) — the scorecard's identity + filename.
        metrics: flat numeric metrics (the trendable series), e.g. ``{"safety_pass": 10, "safety_fail": 0}``.
        cases: optional per-case records ``{"id", "safety": pass|fail|known-gap, "judge": {dim: score}, "reasons"}``.
        models_under_test: the model tag(s) for this run (see ``env_models``).
        prompt_version: the job's prompt-version stamp for this run, if the output carried one (see
            ``capture_prompt_version``). ``None`` when absent — the run-config tag records it as null.

    The ``run_config`` tag captures ``{model, reasoningEffort, promptVersion}`` for the run — the
    attributes a trend needs to explain a step (a model swap, an effort change, a prompt bump). All
    three are TOLERANT: a null value is expected and never an error, so the schema is stable whether or
    not the jobs already stamp a prompt version.
    """
    record = {
        "module": module,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "git_sha": _git_sha(),
        "gateway": gateway_configured(),
        "judge_model": JUDGE_MODEL,
        "models_under_test": models_under_test or [],
        "run_config": {
            "model": (models_under_test or [None])[0],
            "reasoningEffort": env_reasoning_effort(),
            "promptVersion": prompt_version,
        },
        "metrics": metrics,
        "cases": cases or [],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{module}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
