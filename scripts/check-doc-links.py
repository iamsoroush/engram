#!/usr/bin/env python3
"""Check that every relative markdown link in the repo resolves, and enforce doc-layer rules.

Rules enforced:
1. Every relative link target in a tracked ``*.md`` file must exist (anchors are ignored).
2. System-state docs must not link into ``docs/work/`` (the process workspace) — if a
   system-state doc needs that content, it must be folded out first (see docs/work/README.md).

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


def tracked_markdown_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "*.md"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout
    return [REPO / line for line in out.splitlines() if line.strip()]


def main() -> int:
    errors: list[str] = []
    for md in tracked_markdown_files():
        rel_md = md.relative_to(REPO)
        in_work = rel_md.parts[:2] == ("docs", "work")
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
                if not in_work and rel_resolved.parts[:2] == ("docs", "work"):
                    errors.append(
                        f"{rel_md}:{lineno}: system-state doc links into docs/work/ -> {target}"
                        " (fold the content out first; see docs/work/README.md)"
                    )
    if errors:
        print(f"{len(errors)} doc-link violation(s):")
        for err in errors:
            print(f"  {err}")
        return 1
    print("All markdown links resolve; docs/work/ isolation holds.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
