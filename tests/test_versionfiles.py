from __future__ import annotations

from pathlib import Path

import pytest

from conventional_release import semver
from conventional_release.versionfiles import (
    VersionFileError,
    has_version,
    read_version,
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
