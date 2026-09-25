"""Just enough SemVer 2.0: validate, and bump by level."""

from __future__ import annotations

import re

_SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)

LEVELS = ("major", "minor", "patch")


def is_valid(version: str) -> bool:
    return _SEMVER.match(version) is not None


def bump(version: str, level: str) -> str:
    m = _SEMVER.match(version)
    if m is None:
        raise ValueError(f"not a semantic version: {version!r}")
    major, minor, patch = (int(g) for g in m.groups()[:3])
    if level == "major":
        return f"{major + 1}.0.0"
    if level == "minor":
        return f"{major}.{minor + 1}.0"
    if level == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"level must be one of {LEVELS}, not {level!r}")
