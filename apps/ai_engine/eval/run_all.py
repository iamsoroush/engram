#!/usr/bin/env python3
"""Run every AI-job golden-set eval and print one consolidated scorecard.

The single entry point for the eval epic: each AI job (transcription, image caption, report
synthesis = treatments + aftercare + sections, patient memory, patient matching) owns a
``*_eval.py`` module that runs the REAL gateway and exits non-zero on failure. This runner discovers
and runs them, streams each one's output, and prints a per-job pass/fail summary so a prompt or
model change can be gated on the whole suite — not eyeballed one job at a time.

Run where a gateway is reachable::

    docker exec engram-main-ai-engine-1 python /app/eval/run_all.py

No gateway → each eval SKIPS (exit 0); the suite is green but the scorecard says "skipped". With a
gateway it exits non-zero if any eval fails. Add a new job's eval by dropping a ``*_eval.py`` here.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
OUT_DIR = HERE / "out"

# Ordered so the scorecard reads capture → understand → remember. A new eval is picked up by name.
EVALS = [
    "transcription_eval.py",
    "caption_eval.py",
    "treatments_eval.py",
    "aftercare_conflict_eval.py",
    "safety_flags_eval.py",
    "safety_reconcile_eval.py",
    "report_sections_eval.py",
    "patient_memory_eval.py",
    "patient_matching_eval.py",
    "qa_draft_eval.py",
    "qa_revise_eval.py",
]


def merge_scorecards(present: list[str], results: dict[str, int]) -> pathlib.Path | None:
    """Merge every module's ``eval/out/<module>.json`` into one ``eval/out/scorecard.json``.

    Each ``*_eval.py`` emits its own per-module scorecard via ``_common.write_scorecard``; this collects
    them into a single run-level file (flat per-module metrics + tags) that a trend job / experiment
    tracker consumes. Returns the merged path, or None if no module emitted a scorecard.
    """
    modules: dict[str, dict] = {}
    for name in present:
        stem = name[:-3] if name.endswith(".py") else name
        path = OUT_DIR / f"{stem}.json"
        if not path.exists():
            continue
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        record["exit_code"] = results.get(name)
        modules[stem] = record
    if not modules:
        return None
    sample = next(iter(modules.values()))
    merged = {
        "git_sha": sample.get("git_sha"),
        "timestamp": sample.get("timestamp"),
        "gateway": sample.get("gateway"),
        "judge_model": sample.get("judge_model"),
        "summary": {
            "evals_run": len(present),
            "evals_green": sum(1 for name in present if results.get(name) == 0),
            "modules_with_scorecard": len(modules),
        },
        "modules": modules,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / "scorecard.json"
    path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main() -> int:
    present = [name for name in EVALS if (HERE / name).exists()]
    missing = [name for name in EVALS if not (HERE / name).exists()]
    results: dict[str, int] = {}
    for name in present:
        print(f"\n{'=' * 8} {name} {'=' * 8}")
        result = subprocess.run([sys.executable, str(HERE / name)])
        results[name] = result.returncode

    print(f"\n{'=' * 8} SCORECARD {'=' * 8}")
    for name in present:
        status = "PASS" if results[name] == 0 else "FAIL"
        print(f"  {status}  {name}")
    for name in missing:
        print(f"  TODO  {name}  (not yet written — see docs/ai_engine/evals.md)")
    failed = [name for name, code in results.items() if code != 0]
    print(f"\n{len(present) - len(failed)}/{len(present)} evals green; {len(missing)} TODO.")

    merged = merge_scorecards(present, results)
    if merged is not None:
        print(f"Machine-readable scorecard: {merged}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
