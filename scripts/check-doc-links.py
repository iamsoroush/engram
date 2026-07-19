#!/usr/bin/env python3
"""Check that every relative markdown link in the repo resolves, and enforce doc-layer rules.

Rules enforced:
1. Every relative link target in a tracked ``*.md`` file must exist (anchors are ignored).
2. System-state docs must not link into ``work-docs/`` (the process workspace) — if a
   system-state doc needs that content, it must be folded out first (see work-docs/README.md).
3. Any ``docs/...`` or ``work-docs/...`` ``.md``-path mention in ANY tracked text file (code
   comments, docstrings, prose, backticks) must point at a file that exists — stale mentions are
   how deleted process docs keep being cited from code.
4. Every decision file in ``docs/technical-decisions/`` must have an entry in that directory's
   README index — a hand-maintained index is fine exactly because this check keeps it complete.

External (http/https/mailto) links and intra-file anchors are not checked.

Usage: python3 scripts/check-doc-links.py   (exits non-zero on any violation)
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# [text](target) — tolerates titles: [text](target "title")
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")

SKIP_PREFIXES = ("http://", "https://", "mailto:", "tel:", "#", "data:")

# A repo doc path cited in prose/comments anywhere (rule 3). The lookbehind keeps us off
# URL/relative-link fragments like ``../docs/x.md`` (those are rule-1 territory).
DOC_PATH_MENTION_RE = re.compile(r"(?<![\w/.\-])(?:docs|work-docs)/[\w./\-]+\.md\b")

SKIP_MENTION_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".woff", ".woff2",
                         ".wav", ".mp3", ".pdf", ".lock")


def tracked_markdown_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "*.md"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout
    # Vendored third-party skills keep their upstream's internal links — their integrity is the
    # skill author's concern, not this repo's docs contract. Our own docs stay fully checked.
    return [
        REPO / line
        for line in out.splitlines()
        if line.strip() and not line.startswith(".claude/skills/") and not line.startswith(".agents/")
    ]


def tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout
    return [
        REPO / line
        for line in out.splitlines()
        if line.strip() and not line.startswith(".claude/skills/") and not line.startswith(".agents/")
    ]


def main() -> int:
    errors: list[str] = []
    for md in tracked_markdown_files():
        rel_md = md.relative_to(REPO)
        in_work = rel_md.parts[:1] == ("work-docs",)
        text = md.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            for match in LINK_RE.finditer(line):
                target = match.group(1)
                if target.startswith(SKIP_PREFIXES):
                    continue
                # Strip anchor fragments; ignore pure-anchor links.
                path_part = target.split("#", 1)[0]
                if not path_part:
                    continue
                resolved = (md.parent / path_part).resolve()
                if not resolved.exists():
                    errors.append(f"{rel_md}:{lineno}: broken link -> {target}")
                    continue
                try:
                    rel_resolved = resolved.relative_to(REPO)
                except ValueError:
                    errors.append(f"{rel_md}:{lineno}: link escapes the repo -> {target}")
                    continue
                if not in_work and rel_resolved.parts[:1] == ("work-docs",):
                    errors.append(
                        f"{rel_md}:{lineno}: system-state doc links into work-docs/ -> {target}"
                        " (fold the content out first; see work-docs/README.md)"
                    )
    for f in tracked_files():
        if f.suffix.lower() in SKIP_MENTION_SUFFIXES or not f.is_file():
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel_f = f.relative_to(REPO)
        for lineno, line in enumerate(text.splitlines(), start=1):
            for m in DOC_PATH_MENTION_RE.finditer(line):
                if not (REPO / m.group(0)).exists():
                    errors.append(f"{rel_f}:{lineno}: stale doc-path mention -> {m.group(0)}")
    td = REPO / "docs" / "technical-decisions"
    td_readme = td / "README.md"
    if td_readme.exists():
        decision_files = {p.name for p in td.glob("*.md")} - {"README.md"}
        indexed = set(re.findall(r"\]\(([\w.\-]+\.md)\)", td_readme.read_text(encoding="utf-8")))
        for missing in sorted(decision_files - indexed):
            errors.append(
                f"docs/technical-decisions/README.md: decision file missing from the index -> {missing}"
            )
    if errors:
        print(f"{len(errors)} doc-link violation(s):")
        for err in errors:
            print(f"  {err}")
        return 1
    print("All markdown links resolve; work-docs/ isolation holds; doc-path mentions exist.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
