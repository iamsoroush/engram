#!/usr/bin/env python3
"""Render an eval-scorecard time series as a markdown trend report.

The Stage-2 scheduled eval workflow archives each run's merged scorecard to the eval bucket under
``scorecards/<date>-<sha>.json`` (the run-level shape ``run_all.py`` emits — top-level ``git_sha`` /
``timestamp`` / ``judge_model`` / ``gateway`` tags + a ``modules`` map, each module carrying flat
``metrics``, per-case ``judge`` dimension scores, and a ``run_config`` tag). This script reads a local
directory of those files (the workflow mirrors the ``scorecards/`` prefix down first) and prints a
compact markdown trend to stdout — meant to be appended to ``$GITHUB_STEP_SUMMARY``.

It is what makes the **advisory** judge tier actionable: a model/prompt swap on the gateway shows up as
a step in a dimension mean or the safety pass-rate, WITHOUT ever flaking a build. Deterministic here —
no network, no gateway; it only reads JSON.

Usage:
    python3 scripts/eval-trend.py <dir-of-scorecards> [--runs N]
    # dir defaults to apps/ai_engine/eval/out; --runs caps how many recent runs are shown (default 8)
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

DEFAULT_DIR = Path("apps/ai_engine/eval/out")


def load_runs(directory: Path) -> list[dict[str, Any]]:
    """Load every merged scorecard JSON in ``directory``, oldest first.

    Accepts only run-level scorecards (a ``modules`` map); the per-module files and anything
    unparseable are skipped. Sorted by ``timestamp`` then filename so the series reads left→right.
    """
    runs: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(record, dict) or not isinstance(record.get("modules"), dict):
            continue
        record["_file"] = path.name
        runs.append(record)
    runs.sort(key=lambda r: (str(r.get("timestamp") or ""), str(r.get("_file") or "")))
    return runs


def run_label(run: dict[str, Any]) -> str:
    """A short column label for a run: date + short sha (falls back to the filename)."""
    date = str(run.get("timestamp") or "")[:10]
    sha = str(run.get("git_sha") or "")[:7]
    return " ".join(part for part in (date, sha) if part) or str(run.get("_file") or "?")


def judge_means(module_record: dict[str, Any]) -> dict[str, float]:
    """Mean of each judge dimension across a module's cases (empty when the module has no judge tier)."""
    sums: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)
    for case in module_record.get("cases") or []:
        for dim, value in (case.get("judge") or {}).items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                sums[dim] += float(value)
                counts[dim] += 1
    return {dim: sums[dim] / counts[dim] for dim in sums if counts[dim]}


def _metric(module_record: dict[str, Any], key: str) -> int:
    value = (module_record.get("metrics") or {}).get(key)
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0


def module_names(runs: list[dict[str, Any]]) -> list[str]:
    """Every module seen across runs, in first-seen order."""
    seen: list[str] = []
    for run in runs:
        for name in run.get("modules") or {}:
            if name not in seen:
                seen.append(name)
    return seen


def render_safety_table(runs: list[dict[str, Any]], modules: list[str]) -> list[str]:
    """One row per module, one column per run: ``pass/fail`` (``+Nkg`` when known-gaps are present)."""
    header = "| module | " + " | ".join(run_label(r) for r in runs) + " |"
    sep = "| --- | " + " | ".join("---" for _ in runs) + " |"
    lines = ["### Safety gates (deterministic — `pass`/`fail`, `+Nkg` = known-gaps)", "", header, sep]
    for name in modules:
        cells: list[str] = []
        for run in runs:
            record = (run.get("modules") or {}).get(name)
            if not isinstance(record, dict):
                cells.append("·")
                continue
            passed, failed, kg = _metric(record, "safety_pass"), _metric(record, "safety_fail"), _metric(record, "known_gap")
            cell = f"{passed}/{failed}"
            if kg:
                cell += f" +{kg}kg"
            if failed:
                cell = f"**{cell}**"  # bold a regression so it's obvious in the summary
            cells.append(cell)
        lines.append(f"| `{name}` | " + " | ".join(cells) + " |")
    return lines


def render_judge_trend(runs: list[dict[str, Any]], modules: list[str]) -> list[str]:
    """Per-dimension judge means over the run series (advisory tier — drift, never a gate)."""
    lines = ["### Judge dimensions (advisory — 0..1 mean; ↑/↓ vs previous run)", ""]
    any_dim = False
    for name in modules:
        series = [(run, judge_means((run.get("modules") or {}).get(name) or {})) for run in runs]
        dims: list[str] = []
        for _, means in series:
            for dim in means:
                if dim not in dims:
                    dims.append(dim)
        if not dims:
            continue
        any_dim = True
        header = "| " + name + " | " + " | ".join(run_label(r) for r, _ in series) + " |"
        sep = "| --- | " + " | ".join("---" for _ in series) + " |"
        lines += ["", header, sep]
        for dim in dims:
            cells: list[str] = []
            previous: float | None = None
            for _, means in series:
                value = means.get(dim)
                if value is None:
                    cells.append("·")
                    continue
                arrow = ""
                if previous is not None:
                    arrow = " ↑" if value > previous + 0.005 else " ↓" if value < previous - 0.005 else " ="
                cells.append(f"{value:.2f}{arrow}")
                previous = value
            lines.append(f"| {dim} | " + " | ".join(cells) + " |")
    if not any_dim:
        lines.append("_No judge scores recorded in this window (gateway-less runs, or judge unavailable)._")
    return lines


def render_known_gap_ages(runs: list[dict[str, Any]], modules: list[str]) -> list[str]:
    """Active knownGaps in the latest run + how many runs back each first appeared (age)."""
    lines = ["### Active known-gaps (age = runs since first seen — escalate a stale one)", ""]
    if not runs:
        return lines + ["_(no runs)_"]
    latest = runs[-1]
    rows: list[str] = []
    for name in modules:
        record = (latest.get("modules") or {}).get(name)
        if not isinstance(record, dict) or _metric(record, "known_gap") <= 0:
            continue
        first_index = len(runs) - 1
        for index, run in enumerate(runs):
            other = (run.get("modules") or {}).get(name)
            if isinstance(other, dict) and _metric(other, "known_gap") > 0:
                first_index = index
                break
        age = (len(runs) - 1) - first_index
        gap_ids = [c.get("id") for c in (record.get("cases") or []) if c.get("safety") == "known-gap"]
        label = ", ".join(str(i) for i in gap_ids) or "(unnamed)"
        rows.append(f"- `{name}`: {_metric(record, 'known_gap')} known-gap(s) [{label}] — age {age} run(s)")
    return lines + (rows or ["_None active._"])


def render(runs: list[dict[str, Any]], max_runs: int) -> str:
    if not runs:
        return "## AI eval trend\n\n_No scorecards found to trend._"
    window = runs[-max_runs:]
    modules = module_names(window)
    latest = window[-1]
    head = [
        "## AI eval trend",
        "",
        f"- runs shown: **{len(window)}** (of {len(runs)} archived)  ·  judge: `{latest.get('judge_model', '?')}`",
        f"- latest run: **{run_label(latest)}**  ·  gateway: `{latest.get('gateway')}`  ·  "
        f"models: `{', '.join((latest.get('modules') or {}).get(m, {}).get('run_config', {}).get('model') or '' for m in modules[:1]) or '—'}`",
        "",
    ]
    parts = [
        "\n".join(head),
        "\n".join(render_safety_table(window, modules)),
        "",
        "\n".join(render_judge_trend(window, modules)),
        "",
        "\n".join(render_known_gap_ages(window, modules)),
    ]
    return "\n".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render an eval-scorecard time series as markdown.")
    parser.add_argument("directory", nargs="?", default=str(DEFAULT_DIR),
                        help="dir of archived merged scorecards (default: apps/ai_engine/eval/out)")
    parser.add_argument("--runs", type=int, default=8, help="max recent runs to show (default 8)")
    args = parser.parse_args()

    directory = Path(args.directory)
    if not directory.is_dir():
        print(f"## AI eval trend\n\n_No scorecard directory at `{directory}`._")
        return 0
    runs = load_runs(directory)
    print(render(runs, max(1, args.runs)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
