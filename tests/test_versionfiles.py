from __future__ import annotations

from pathlib import Path

import pytest

from conventional_release import semver
from conventional_release.versionfiles import (
    VersionFileError,
    has_version,
    read_version,
    sync_lock,
    write_version,
)

PYPROJECT = """\
[build-system]
requires = ["hatchling"]

[project]
name = "x"  # the name
version = "1.2.3"  # keep this comment
dependencies = []

[tool.other]
version = "9.9.9"
"""


def test_pyproject_edits_only_the_project_version(tmp_path: Path) -> None:
    path = tmp_path / "pyproject.toml"
    path.write_text(PYPROJECT)
    assert read_version(path) == "1.2.3"
    write_version(path, "1.3.0")
    assert path.read_text() == PYPROJECT.replace('"1.2.3"', '"1.3.0"')


def test_poetry_table(tmp_path: Path) -> None:
    path = tmp_path / "pyproject.toml"
    path.write_text("[tool.poetry]\nname = 'x'\nversion = '0.1.0'\n")
    write_version(path, "0.2.0")
    assert path.read_text() == "[tool.poetry]\nname = 'x'\nversion = '0.2.0'\n"


def test_dynamic_version_is_not_a_version_file(tmp_path: Path) -> None:
    path = tmp_path / "pyproject.toml"
    path.write_text('[project]\nname = "x"\ndynamic = ["version"]\n')
    assert not has_version(path)


def test_cargo_workspace_package(tmp_path: Path) -> None:
    path = tmp_path / "Cargo.toml"
    path.write_text('[workspace]\nmembers = ["a"]\n\n[workspace.package]\nversion = "0.4.0"\n')
    write_version(path, "0.5.0")
    assert read_version(path) == "0.5.0"


def test_package_json_keeps_formatting(tmp_path: Path) -> None:
    path = tmp_path / "package.json"
    text = '{\n    "name": "x",\n    "version": "2.0.0",\n    "deps": {"y": "2.0.0"}\n}\n'
    path.write_text(text)
    write_version(path, "2.1.0")
    assert path.read_text() == text.replace('"version": "2.0.0"', '"version": "2.1.0"')


def test_plain_file(tmp_path: Path) -> None:
    path = tmp_path / "VERSION"
    path.write_text("0.9.0\n")
    write_version(path, "1.0.0")
    assert path.read_text() == "1.0.0\n"


def test_plain_file_must_be_one_line(tmp_path: Path) -> None:
    path = tmp_path / "VERSION"
    path.write_text("1.0.0\nextra\n")
    with pytest.raises(VersionFileError):
        read_version(path)


UV_LOCK = """\
version = 1
revision = 3
requires-python = ">=3.11"

[[package]]
name = "click"
version = "1.2.3"
source = { registry = "https://pypi.org/simple" }

[[package]]
name = "my-tool"
version = "1.2.3"
source = { editable = "." }
dependencies = [
    { name = "click" },
]

[package.metadata]
requires-dist = [{ name = "click" }]
"""


def test_uv_lock_follows_the_project_version(tmp_path: Path) -> None:
    manifest = tmp_path / "pyproject.toml"
    manifest.write_text('[project]\nname = "My_Tool"\nversion = "1.2.3"\n')
    lock = tmp_path / "uv.lock"
    lock.write_text(UV_LOCK)
    assert sync_lock(manifest, "1.3.0") == lock
    assert lock.read_text() == UV_LOCK.replace(
        'name = "my-tool"\nversion = "1.2.3"', 'name = "my-tool"\nversion = "1.3.0"'
    )
    assert sync_lock(manifest, "1.3.0") is None  # already in step


def test_cargo_lock_follows_the_crate_version(tmp_path: Path) -> None:
    manifest = tmp_path / "Cargo.toml"
    manifest.write_text('[package]\nname = "tool"\nversion = "0.1.0"\n')
    lock = tmp_path / "Cargo.lock"
    lock.write_text('version = 4\n\n[[package]]\nname = "tool"\nversion = "0.1.0"\n')
    assert sync_lock(manifest, "0.2.0") == lock
    assert lock.read_text().endswith('name = "tool"\nversion = "0.2.0"\n')


def test_no_lock_to_sync(tmp_path: Path) -> None:
    manifest = tmp_path / "pyproject.toml"
    manifest.write_text('[project]\nversion = "1.2.3"\n')  # no name
    assert sync_lock(manifest, "1.3.0") is None  # no uv.lock
    (tmp_path / "uv.lock").write_text(UV_LOCK)
    assert sync_lock(manifest, "1.3.0") is None  # the manifest names no project
    manifest.write_text('[project]\nname = "other"\nversion = "1.2.3"\n')
    assert sync_lock(manifest, "1.3.0") is None  # the lock has no entry for it
    assert (tmp_path / "uv.lock").read_text() == UV_LOCK
    assert sync_lock(tmp_path / "VERSION", "1.3.0") is None  # no lock kind for plain files


@pytest.mark.parametrize(
    ("version", "level", "expected"),
    [
        ("1.2.3", "major", "2.0.0"),
        ("1.2.3", "minor", "1.3.0"),
        ("1.2.3", "patch", "1.2.4"),
        ("1.2.3-rc.1", "patch", "1.2.4"),
    ],
)
def test_bump(version: str, level: str, expected: str) -> None:
    assert semver.bump(version, level) == expected


def test_semver_validation() -> None:
    assert semver.is_valid("1.0.0-rc.1+build.5")
    assert not semver.is_valid("01.0.0")
    assert not semver.is_valid("1.0")
    with pytest.raises(ValueError):
        semver.bump("1.0.0", "huge")
