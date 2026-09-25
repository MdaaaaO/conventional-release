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
_TOML_LOCKS = {
    "pyproject.toml": ("uv.lock", "project"),
    "Cargo.toml": ("Cargo.lock", "package"),
}
# npm repeats the version at the top level and in packages[""]; `npm ci` rejects a mismatch.
_NPM_LOCKS = ("package-lock.json", "npm-shrinkwrap.json")


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


def sync_locks(manifest: Path, version: str) -> list[Path]:
    """Set the project's own version in the lock files next to `manifest`; return those changed.

    A lock file that is missing, has no entry for the project, or already says `version` is left
    alone: there is nothing to keep in step.
    """
    if manifest.name == "package.json":
        locks = [_sync_npm_lock(manifest.with_name(name), version) for name in _NPM_LOCKS]
        return [lock for lock in locks if lock]
    lock = _sync_toml_lock(manifest, version)
    return [lock] if lock else []


def _sync_toml_lock(manifest: Path, version: str) -> Path | None:
    spec = _TOML_LOCKS.get(manifest.name)
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


def _npm_root(lock: dict[str, object]) -> dict[str, object] | None:
    """packages[""], the project's own entry, when the lock has one."""
    packages = lock.get("packages")
    root = packages.get("") if isinstance(packages, dict) else None
    return root if isinstance(root, dict) else None


def _sync_npm_lock(lock: Path, version: str) -> Path | None:
    """Edit the top-level "version" and the one in packages[""] (lockfileVersion 2 and 3).

    npm writes `name`, `version` first in both objects, so each is the first "version" key from
    where the object starts. The result is parsed back to prove the edit hit exactly those two.
    """
    if not lock.exists():
        return None
    text = lock.read_text()
    data = json.loads(text)
    if not isinstance(data, dict) or not isinstance(data.get("version"), str):
        return None
    root = _npm_root(data)
    if data["version"] == version and (
        not isinstance(root, dict) or root.get("version") == version
    ):
        return None
    key = re.compile(r'("version"\s*:\s*")[^"]*"')
    new = key.sub(lambda m: m.group(1) + version + '"', text, count=1)
    if isinstance(root, dict) and "version" in root:
        at = re.search(r'"packages"\s*:\s*\{\s*""\s*:\s*\{', new)
        if at is None:
            raise VersionFileError(f'{lock.name}: could not locate packages[""]')
        new = new[: at.end()] + key.sub(
            lambda m: m.group(1) + version + '"', new[at.end() :], count=1
        )
    check = json.loads(new)
    root_after = _npm_root(check) or {}
    if check["version"] != version or (
        "version" in root_after and root_after["version"] != version
    ):
        raise VersionFileError(f"{lock.name}: could not locate the version strings")
    lock.write_text(new)
    return lock
