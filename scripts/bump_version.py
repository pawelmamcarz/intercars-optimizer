#!/usr/bin/env python3
"""
Auto version bumper — Tesla-style: YYYY.WW.BUILD

Format: 2026.16.3 = year 2026, ISO week 16, build 3.
Each commit increments BUILD. When the week rolls over, BUILD resets
to 1 automatically. No manual minor/major/patch — the calendar drives
the meaning.

Usage:
    python scripts/bump_version.py          # auto bump → 2026.16.4
    python scripts/bump_version.py set 2026.16.1  # explicit set

Updates version in:
  - app/config.py          (app_version)
  - app/static/index.html  (<title> + badge)
  - app/static/superadmin.html (if present)
"""
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent.parent

CONFIG = ROOT / "app" / "config.py"
INDEX_HTML = ROOT / "app" / "static" / "index.html"
SUPERADMIN_HTML = ROOT / "app" / "static" / "superadmin.html"

# Match both old semver (5.1.66) and Tesla (2026.16.3)
_VERSION_RE = re.compile(r'app_version:\s*str\s*=\s*"([\d.]+)"')


def read_current_version() -> str:
    text = CONFIG.read_text()
    m = _VERSION_RE.search(text)
    if not m:
        raise ValueError("Cannot find app_version in config.py")
    return m.group(1)


def tesla_bump(current: str) -> str:
    """Increment the build counter, or roll to a new week if the
    calendar moved past the version's week."""
    today = date.today()
    iso = today.isocalendar()
    year, week = iso[0], iso[1]

    parts = current.split(".")
    if len(parts) == 3:
        try:
            cur_year, cur_week, cur_build = int(parts[0]), int(parts[1]), int(parts[2])
        except ValueError:
            cur_year, cur_week, cur_build = 0, 0, 0
    else:
        cur_year, cur_week, cur_build = 0, 0, 0

    if cur_year == year and cur_week == week:
        return f"{year}.{week}.{cur_build + 1}"
    return f"{year}.{week}.1"


def update_file(path: Path, old_ver: str, new_ver: str) -> bool:
    if not path.exists():
        return False
    text = path.read_text()
    updated = text.replace(f'"{old_ver}"', f'"{new_ver}"')
    updated = updated.replace(f"v{old_ver}", f"v{new_ver}")
    if updated != text:
        path.write_text(updated)
        return True
    return False


def main():
    old_ver = read_current_version()

    if len(sys.argv) >= 3 and sys.argv[1] == "set":
        new_ver = sys.argv[2]
    else:
        new_ver = tesla_bump(old_ver)

    if new_ver == old_ver:
        print(f"Version unchanged: {old_ver}")
        return

    files_updated = []
    for f in [CONFIG, INDEX_HTML, SUPERADMIN_HTML]:
        if update_file(f, old_ver, new_ver):
            files_updated.append(str(f.relative_to(ROOT)))

    print(f"{old_ver} → {new_ver}")
    for f in files_updated:
        print(f"  updated: {f}")


if __name__ == "__main__":
    main()
