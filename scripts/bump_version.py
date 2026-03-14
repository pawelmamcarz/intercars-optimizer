#!/usr/bin/env python3
"""
Auto version bumper for Flow Procurement Platform.

Usage:
    python scripts/bump_version.py          # patch: 5.0.0 → 5.0.1
    python scripts/bump_version.py minor    # minor: 5.0.3 → 5.1.0
    python scripts/bump_version.py major    # major: 5.1.2 → 6.0.0
    python scripts/bump_version.py set 5.2.0  # explicit set

Updates version in:
  - app/config.py          (app_version)
  - app/static/index.html  (<title> + badge)
  - app/static/superadmin.html (if present)
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent

# ── Files to update ──────────────────────────────────────────────────────
CONFIG = ROOT / "app" / "config.py"
INDEX_HTML = ROOT / "app" / "static" / "index.html"
SUPERADMIN_HTML = ROOT / "app" / "static" / "superadmin.html"


def read_current_version() -> str:
    """Read current version from config.py."""
    text = CONFIG.read_text()
    m = re.search(r'app_version:\s*str\s*=\s*"(\d+\.\d+\.\d+)"', text)
    if not m:
        raise ValueError("Cannot find app_version in config.py")
    return m.group(1)


def bump(version: str, part: str) -> str:
    """Bump version string."""
    major, minor, patch = [int(x) for x in version.split(".")]
    if part == "patch":
        patch += 1
    elif part == "minor":
        minor += 1
        patch = 0
    elif part == "major":
        major += 1
        minor = 0
        patch = 0
    return f"{major}.{minor}.{patch}"


def update_file(path: Path, old_ver: str, new_ver: str):
    """Replace version strings in a file."""
    if not path.exists():
        return False
    text = path.read_text()
    old_short = f"v{old_ver.rsplit('.', 1)[0]}"  # v5.0
    new_short = f"v{new_ver.rsplit('.', 1)[0]}"  # v5.1

    updated = text
    # Full version (config.py)
    updated = updated.replace(f'"{old_ver}"', f'"{new_ver}"')
    # Short version in HTML (v5.0 → v5.1)
    if old_short != new_short:
        updated = updated.replace(old_short, new_short)

    if updated != text:
        path.write_text(updated)
        return True
    return False


def main():
    old_ver = read_current_version()

    # Parse args
    if len(sys.argv) >= 3 and sys.argv[1] == "set":
        new_ver = sys.argv[2]
    elif len(sys.argv) >= 2:
        part = sys.argv[1]
        if part not in ("patch", "minor", "major"):
            print(f"Usage: {sys.argv[0]} [patch|minor|major|set X.Y.Z]")
            sys.exit(1)
        new_ver = bump(old_ver, part)
    else:
        new_ver = bump(old_ver, "patch")

    if new_ver == old_ver:
        print(f"Version unchanged: {old_ver}")
        return

    # Update all files
    files_updated = []
    for f in [CONFIG, INDEX_HTML, SUPERADMIN_HTML]:
        if update_file(f, old_ver, new_ver):
            files_updated.append(str(f.relative_to(ROOT)))

    print(f"{old_ver} → {new_ver}")
    for f in files_updated:
        print(f"  updated: {f}")

    return new_ver


if __name__ == "__main__":
    main()
