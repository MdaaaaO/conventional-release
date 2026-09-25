"""Project configuration: `.conventional-release.toml`, or `[tool.conventional-release]` in
pyproject.toml. Every key is optional; the defaults reproduce standard-version's behaviour."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CONFIG_FILE = ".conventional-release.toml"


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class CommitType:
    type: str
    section: str
    hidden: bool = False


# The Angular set, which Conventional Commits grew out of, in the order standard-version's
# `.versionrc` examples use. Every type gets a section by default; set `hidden = true` to drop one.
DEFAULT_TYPES: tuple[CommitType, ...] = (
    CommitType("feat", "Features"),
    CommitType("fix", "Bug Fixes"),
    CommitType("docs", "Documentation"),
    CommitType("style", "Styling"),
    CommitType("refactor", "Refactors"),
    CommitType("perf", "Performance"),
    CommitType("test", "Tests"),
    CommitType("build", "Build System"),
    CommitType("ci", "CI"),
    CommitType("chore", "Chore"),
    CommitType("revert", "Reverts"),
)

VERSION_SOURCES = ("file", "tag")
CHANGELOG_MODES = ("prepend", "regenerate")

# Probed in this order when `version-files` is not set and `version-source = "file"`.
AUTODETECT_FILES = ("pyproject.toml", "package.json", "Cargo.toml", "VERSION", "version")


@dataclass(frozen=True)
class Config:
    root: Path
    version_source: str = "file"
    version_files: tuple[str, ...] = ()
    changelog: str = "CHANGELOG.md"
    changelog_mode: str = "prepend"
    tag_prefix: str = "v"
    base_branch: str = "main"
    branch_prefix: str = "release/"
    initial_version: str = "0.1.0"
    repo_url: str | None = None
    cliff_config: str | None = None
    subject_lowercase: bool = True
    types: tuple[CommitType, ...] = field(default=DEFAULT_TYPES)

    @property
    def changelog_path(self) -> Path:
        return self.root / self.changelog

    def tag(self, version: str) -> str:
        return f"{self.tag_prefix}{version}"

    def branch(self, version: str) -> str:
        return f"{self.branch_prefix}{self.tag(version)}"


_SCALAR_KEYS = {
    "version-source": ("version_source", str),
    "changelog": ("changelog", str),
    "changelog-mode": ("changelog_mode", str),
    "tag-prefix": ("tag_prefix", str),
    "base-branch": ("base_branch", str),
    "branch-prefix": ("branch_prefix", str),
    "initial-version": ("initial_version", str),
    "repo-url": ("repo_url", str),
    "cliff-config": ("cliff_config", str),
    "subject-lowercase": ("subject_lowercase", bool),
}


def _raw(root: Path) -> tuple[dict[str, Any], str]:
    dedicated = root / CONFIG_FILE
    if dedicated.is_file():
        with dedicated.open("rb") as f:
            return tomllib.load(f), CONFIG_FILE
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        with pyproject.open("rb") as f:
            data = tomllib.load(f)
        section = data.get("tool", {}).get("conventional-release")
        if section is not None:
            return section, "pyproject.toml [tool.conventional-release]"
    return {}, "defaults"


def load(root: Path) -> Config:
    raw, where = _raw(root)
    kwargs: dict[str, Any] = {}
    for key, value in raw.items():
        if key in _SCALAR_KEYS:
            name, kind = _SCALAR_KEYS[key]
            if not isinstance(value, kind):
                raise ConfigError(f"{where}: {key} must be a {kind.__name__}")
            kwargs[name] = value
        elif key == "version-files":
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise ConfigError(f"{where}: version-files must be a list of paths")
            kwargs["version_files"] = tuple(value)
        elif key == "types":
            kwargs["types"] = _types(value, where)
        else:
            raise ConfigError(f"{where}: unknown key {key!r}")

    config = Config(root=root, **kwargs)
    if config.version_source not in VERSION_SOURCES:
        raise ConfigError(f"{where}: version-source must be one of {VERSION_SOURCES}")
    if config.changelog_mode not in CHANGELOG_MODES:
        raise ConfigError(f"{where}: changelog-mode must be one of {CHANGELOG_MODES}")
    return config


def _types(value: Any, where: str) -> tuple[CommitType, ...]:
    if not isinstance(value, list) or not value:
        raise ConfigError(f"{where}: types must be a non-empty array of tables")
    out = []
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get("type"), str):
            raise ConfigError(f"{where}: every types entry needs a string 'type'")
        section = item.get("section", item["type"])
        hidden = item.get("hidden", False)
        if not isinstance(section, str) or not isinstance(hidden, bool):
            raise ConfigError(f"{where}: types.{item['type']}: section is a string, hidden a bool")
        out.append(CommitType(item["type"], section, hidden))
    return tuple(out)


def version_files(config: Config) -> list[Path]:
    """The files that carry the version, auto-detected when not configured."""
    if config.version_source == "tag":
        return []
    if config.version_files:
        paths = [config.root / p for p in config.version_files]
        missing = [str(p.relative_to(config.root)) for p in paths if not p.is_file()]
        if missing:
            raise ConfigError(f"version-files not found: {', '.join(missing)}")
        return paths
    from conventional_release import versionfiles

    for name in AUTODETECT_FILES:
        path = config.root / name
        if path.is_file() and versionfiles.has_version(path):
            return [path]
    raise ConfigError(
        "no version file found (looked for " + ", ".join(AUTODETECT_FILES) + "). "
        'Set version-files, or version-source = "tag" if the git tag is the version.'
    )
