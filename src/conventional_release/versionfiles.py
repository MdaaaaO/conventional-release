"""Read and write the version in the files that carry it — standard-version's `bumpFiles`.

Writes are textual edits of the one line that holds the version, so comments, key order and
formatting in the rest of the file survive.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path


class VersionFileError(Exception):
    pass


# file name -> the TOML tables to look in, first match wins
_TOML_TABLES = {
    "pyproject.toml": ("project", "tool.poetry"),
    "Cargo.toml": ("package", "workspace.package"),
}

_HEADER = re.compile(r"^\s*\[\[?\s*([^\]]+?)\s*\]\]?\s*(#.*)?$")
_VERSION_LINE = re.compile(r"""^(\s*version\s*=\s*)(["'])([^"']*)\2""")
_NAME_LINE = re.compile(r"""^\s*name\s*=\s*(["'])([^"']*)\1""")

# manifest -> (its lock file, the manifest table naming the project). The lock records the
# project itself as a [[package]] entry with the version, so a bump that skips it leaves
# `uv run --locked` / `cargo build --locked` failing on the release branch.
_LOCKS = {
    "pyproject.toml": ("uv.lock", "project"),
    "Cargo.toml": ("Cargo.lock", "package"),
}


def _toml_version(path: Path) -> tuple[str, str] | None:
    """(table, version) for the first table in _TOML_TABLES that has a static version."""
    with path.open("rb") as f:
        data = tomllib.load(f)
    for table in _TOML_TABLES[path.name]:
        node: object = data
        for part in table.split("."):
            node = node.get(part) if isinstance(node, dict) else None
        if isinstance(node, dict) and isinstance(node.get("version"), str):
            return table, node["version"]
    return None


def has_version(path: Path) -> bool:
    try:
        read_version(path)
    except VersionFileError:
        return False
    return True


def read_version(path: Path) -> str:
    if path.name in _TOML_TABLES:
        found = _toml_version(path)
        if found is None:
            raise VersionFileError(f"{path.name}: no static version in {_TOML_TABLES[path.name]}")
        return found[1]
    if path.suffix == ".json":
        data = json.loads(path.read_text())
        if not isinstance(data, dict) or not isinstance(data.get("version"), str):
            raise VersionFileError(f'{path.name}: no top-level "version" string')
        found_version: str = data["version"]
        return found_version
    text = path.read_text().strip()
    if not text or "\n" in text:
        raise VersionFileError(f"{path.name}: a plain version file holds exactly one line")
    return text


def write_version(path: Path, version: str) -> None:
    current = read_version(path)
    text = path.read_text()
    if path.name in _TOML_TABLES:
        found = _toml_version(path)
        assert found is not None  # read_version succeeded
        new = _toml_set(text, found[0], version)
    elif path.suffix == ".json":
        pattern = re.compile(r'("version"\s*:\s*")' + re.escape(current) + '"')
        new, n = pattern.subn(lambda m: m.group(1) + version + '"', text, count=1)
        if n != 1:
            raise VersionFileError(f"{path.name}: could not locate the version string")
    else:
        new = text.replace(current, version, 1)
    path.write_text(new)


def _toml_set(text: str, table: str, version: str) -> str:
    lines = text.splitlines(keepends=True)
    in_table = False
    for i, line in enumerate(lines):
        header = _HEADER.match(line)
        if header:
            in_table = header.group(1) == table
            continue
        if in_table and (m := _VERSION_LINE.match(line)):
            lines[i] = m.group(1) + m.group(2) + version + m.group(2) + line[m.end() :]
            return "".join(lines)
    raise VersionFileError(f"no `version = ...` line in [{table}]")


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def sync_lock(manifest: Path, version: str) -> Path | None:
    """Set the project's own [[package]] version in the lock file next to `manifest`.

    Returns the lock file when it changed; None when there is no lock file, the manifest names
    no project, or the lock has no entry for it (nothing to keep in step).
    """
    spec = _LOCKS.get(manifest.name)
    if spec is None or not (lock := manifest.with_name(spec[0])).exists():
        return None
    with manifest.open("rb") as f:
        table = tomllib.load(f).get(spec[1])
    name = table.get("name") if isinstance(table, dict) else None
    if not isinstance(name, str):
        return None
    lines = lock.read_text().splitlines(keepends=True)
    in_package = is_project = False
    for i, line in enumerate(lines):
        if _HEADER.match(line):
            in_package, is_project = line.strip() == "[[package]]", False
        elif in_package and (m := _NAME_LINE.match(line)):
            is_project = _normalize(m.group(2)) == _normalize(name)
        elif is_project and (m := _VERSION_LINE.match(line)):
            if m.group(3) == version:
                return None
            lines[i] = m.group(1) + m.group(2) + version + m.group(2) + line[m.end() :]
            lock.write_text("".join(lines))
            return lock
    return None
