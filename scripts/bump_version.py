#!/usr/bin/env python3
"""Bump the SpeiiDev version from ONE place.

Usage:
    python scripts/bump_version.py 1.2.3

What it updates:
  - src/autodev/_version.py  (the single source of truth)
  - package.json             (npm wrapper; Node can't read the Python file)

Not needed (they read the version dynamically):
  - pyproject.toml  -> [tool.setuptools.dynamic] attr = autodev._version.__version__
  - src/autodev/cli.py -> APP_VERSION = autodev._version.__version__

Pass --check to verify all files agree without changing anything (used by tests).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / "src" / "autodev" / "_version.py"
PACKAGE_JSON = ROOT / "package.json"

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.\-]+)?$")


def read_source_version() -> str:
    text = VERSION_FILE.read_text(encoding="utf-8")
    m = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
    if not m:
        raise SystemExit(f"❌ Could not find __version__ in {VERSION_FILE}")
    return m.group(1)


def read_package_version() -> str:
    data = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    return str(data.get("version", ""))


def write_source_version(version: str) -> None:
    text = VERSION_FILE.read_text(encoding="utf-8")
    text = re.sub(
        r'^(__version__\s*=\s*)["\'][^"\']+["\']',
        rf'\1"{version}"',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    VERSION_FILE.write_text(text, encoding="utf-8")


def write_package_version(version: str) -> None:
    text = PACKAGE_JSON.read_text(encoding="utf-8")
    text = re.sub(
        r'("version"\s*:\s*)["\'][^"\']+["\']',
        rf'\1"{version}"',
        text,
        count=1,
    )
    PACKAGE_JSON.write_text(text, encoding="utf-8")


def check() -> int:
    src = read_source_version()
    pkg = read_package_version()
    ok = src == pkg
    print(f"  src/autodev/_version.py : {src}")
    print(f"  package.json            : {pkg}")
    if ok:
        print(f"✓ Versions agree ({src})")
        return 0
    print("❌ Versions differ — run: python scripts/bump_version.py <version>")
    return 1


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[1] in ("--check", "-c"):
        return check()
    if len(argv) != 2:
        print(__doc__)
        return 2

    version = argv[1].strip().lstrip("v")
    if not SEMVER_RE.match(version):
        print(f"❌ Invalid version '{version}'. Expected something like 1.2.3")
        return 2

    old = read_source_version()
    write_source_version(version)
    write_package_version(version)

    print(f"✅ SpeiiDev version: {old} → {version}")
    print("   updated: src/autodev/_version.py, package.json")
    print("   pyproject.toml & cli.py read it dynamically.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
