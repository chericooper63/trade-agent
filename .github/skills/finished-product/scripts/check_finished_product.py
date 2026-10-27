#!/usr/bin/env python3
"""Minimal project-aware quality gate for the finished-product skill.

This script checks for three high-signal signs of a finished artifact:
1. A Python project structure is present.
2. The repository has a tests directory or test command available.
3. The package metadata or environment configuration is present.

It is intentionally lightweight and should be used as a companion reference,
not as a replacement for the real repository test suite.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def main() -> int:
    required_markers = [
        ROOT / "pyproject.toml",
        ROOT / "tests",
    ]
    checks = []
    for marker in required_markers:
        checks.append((marker.name, marker.exists()))

    project_present = all(exists for _, exists in checks)
    package_config_present = (ROOT / "pyproject.toml").exists()

    print("Finished product quality gate")
    for name, exists in checks:
        print(f"- {name}: {'OK' if exists else 'MISSING'}")

    if not project_present:
        print("FAIL: repository structure is incomplete for a finished product.")
        return 1

    if not package_config_present:
        print("FAIL: pyproject metadata is missing.")
        return 1

    print("PASS: repository structure and package metadata are present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
