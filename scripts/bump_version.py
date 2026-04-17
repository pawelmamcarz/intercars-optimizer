#!/usr/bin/env python3
"""
Auto version bumper — Tesla-style: YYYY.WW.BUILD.PATCH

Format: 2026.16.3.1 = year 2026, ISO week 16, build 3, patch 1.

Semantics:
  - BUILD = increments on every commit within the same ISO week,
           resets to 1 when the week rolls over. PATCH resets to 0.
  - PATCH = manual hotfix counter within a BUILD. Never auto-bumped.

Source of truth: `.version` at repo root (read by app/config.py at import).
Mirrored into: app/static/index.html (<title>, badge, footer, comment),
               app/static/superadmin.html (if present).

Usage:
    python scripts/bump_version.py              # BUILD+1 (or week-roll)
    python scripts/bump_version.py patch        # PATCH+1, keep BUILD
    python scripts/bump_version.py set 2026.17.1.0
"""
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent.parent
VERSION_FILE = ROOT / ".version"
INDEX_HTML = ROOT / "app" / "static" / "index.html"
SUPERADMIN_HTML = ROOT / "app" / "static" / "superadmin.html"

MIRRORED = [INDEX_HTML, SUPERADMIN_HTML]


def read_version() -> str:
    return VERSION_FILE.read_text().strip()


def parse(v: str):
    parts = v.split(".")
    if len(parts) == 3:
        y, w, b = (int(p) for p in parts)
        return y, w, b, 0
    if len(parts) == 4:
        return tuple(int(p) for p in parts)
    raise ValueError(f"Unexpected version format: {v!r}")


def tesla_build_bump(current: str) -> str:
    today = date.today()
    iso = today.isocalendar()
    year, week = iso[0], iso[1]
    cy, cw, cb, _ = parse(current)
    if cy == year and cw == week:
        return f"{year}.{week}.{cb + 1}.0"
    return f"{year}.{week}.1.0"


def patch_bump(current: str) -> str:
    y, w, b, p = parse(current)
    return f"{y}.{w}.{b}.{p + 1}"


def update_file(path: Path, old: str, new: str) -> bool:
    if not path.exists():
        return False
    text = path.read_text()
    updated = text.replace(f'"{old}"', f'"{new}"').replace(f"v{old}", f"v{new}")
    if updated == text:
        return False
    path.write_text(updated)
    return True


def main():
    old = read_version()

    if len(sys.argv) >= 3 and sys.argv[1] == "set":
        new = sys.argv[2]
        parse(new)  # validate
    elif len(sys.argv) >= 2 and sys.argv[1] == "patch":
        new = patch_bump(old)
    else:
        new = tesla_build_bump(old)

    if new == old:
        print(f"Version unchanged: {old}")
        return

    VERSION_FILE.write_text(new + "\n")
    updated = [".version"]
    for f in MIRRORED:
        if update_file(f, old, new):
            updated.append(str(f.relative_to(ROOT)))

    print(f"{old} → {new}")
    for f in updated:
        print(f"  updated: {f}")


if __name__ == "__main__":
    main()
