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

import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent

# Ordered so the scorecard reads capture → understand → remember. A new eval is picked up by name.
EVALS = [
    "transcription_eval.py",
    "caption_eval.py",
    "treatments_eval.py",
    "aftercare_conflict_eval.py",
    "report_sections_eval.py",
    "patient_memory_eval.py",
    "patient_matching_eval.py",
]


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
        print(f"  TODO  {name}  (not yet written — see docs/ai_engine/eval-epic.md)")
    failed = [name for name, code in results.items() if code != 0]
    print(f"\n{len(present) - len(failed)}/{len(present)} evals green; {len(missing)} TODO.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
