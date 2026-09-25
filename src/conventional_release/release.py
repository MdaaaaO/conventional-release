"""The release flow for a protected default branch.

Local half (`release`): branch `release/vX.Y.Z`, update CHANGELOG.md and the version files,
commit `chore(release): X.Y.Z`, push, open a PR. Nothing is tagged here — a tag on the release
branch would point at a commit that never lands once the PR is squash-merged.

CI half (`detect` + `tag`): when a `chore(release): X.Y.Z` commit reaches the default branch,
tag *that* commit and publish the release notes (`notes`).
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from conventional_release import cliff, git, semver, versionfiles
from conventional_release.config import Config, ConfigError, version_files

RELEASE_SUBJECT = re.compile(r"^chore\(release\): (\S+)$")
_PR_SUFFIX = re.compile(r"\s\(#\d+\)$")


class ReleaseError(Exception):
    pass


def current_version(config: Config) -> str | None:
    """The version the project is at now; None before the first release in tag mode."""
    if config.version_source == "tag":
        tag = git.latest_tag(config.root, config.tag_prefix)
        return tag.removeprefix(config.tag_prefix) if tag else None
    found = {p.name: versionfiles.read_version(p) for p in version_files(config)}
    if len(set(found.values())) > 1:
        listed = ", ".join(f"{k}={v}" for k, v in found.items())
        raise ReleaseError(f"version files disagree: {listed}")
    return next(iter(found.values()))


def next_version(config: Config, requested: str | None = None) -> str:
    """`requested` is a level (major|minor|patch), an explicit version, or None to infer."""
    if requested is None:
        return cliff.bumped_version(config)
    if requested in semver.LEVELS:
        base = current_version(config) or config.initial_version
        return semver.bump(base, requested)
    if semver.is_valid(requested.removeprefix(config.tag_prefix)):
        return requested.removeprefix(config.tag_prefix)
    raise ReleaseError(f"not a level or a semantic version: {requested!r}")


def plan(config: Config, requested: str | None = None) -> tuple[str | None, str]:
    current = current_version(config)
    nxt = next_version(config, requested)
    released_before = git.latest_tag(config.root, config.tag_prefix) is not None
    # A project's version file starts at the version its *first* release will carry, so
    # next == current is normal exactly once: before any release tag exists.
    if nxt == current and released_before:
        raise ReleaseError(
            f"next version equals the current one ({current}) — nothing to release. "
            f"Conventional commits since {config.tag(current)}?"
        )
    if git.tag_exists(config.root, config.tag(nxt)):
        raise ReleaseError(f"tag {config.tag(nxt)} already exists")
    return current, nxt


def prepend(path: Path, section: str) -> None:
    """Insert `section` above the newest release, keeping everything already in the file."""
    section = section.strip() + "\n"
    if not path.exists():
        path.write_text(cliff.HEADER + section)
        return
    lines = path.read_text().splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.startswith("## "):
            lines[i:i] = [section, "\n"]
            break
    else:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        if lines and lines[-1].strip():
            lines.append("\n")
        lines.append(section)
    path.write_text("".join(lines))


def notes(config: Config, version: str) -> str:
    """One version's section of the changelog, heading excluded — the release notes."""
    version = version.removeprefix(config.tag_prefix)
    heading = re.compile(r"^## \[?" + re.escape(version) + r"(\]|\s|$)")
    out: list[str] = []
    found = False
    for line in config.changelog_path.read_text().splitlines():
        if found and line.startswith("## "):
            break
        if found:
            out.append(line)
        elif heading.match(line):
            found = True
    if not found:
        raise ReleaseError(f"no section for {version} in {config.changelog}")
    return "\n".join(out).strip("\n") + "\n"


def cut(config: Config, requested: str | None, *, push: bool = True, open_pr: bool = True) -> str:
    root = config.root
    if dirty := git.status_porcelain(root):
        raise ReleaseError(f"working tree is dirty — commit or stash first:\n{dirty}")
    _, version = plan(config, requested)
    branch = config.branch(version)
    if git.branch_exists(root, branch):
        raise ReleaseError(f"branch {branch} already exists")

    section = cliff.unreleased_section(config, version)
    git.run(root, "checkout", "-b", branch)
    if config.changelog_mode == "regenerate":
        cliff.regenerate(config, version)
    else:
        prepend(config.changelog_path, section)
    files = version_files(config)
    for path in files:
        versionfiles.write_version(path, version)
    locks = [lock for path in files for lock in versionfiles.sync_locks(path, version)]

    changed = (str(p.relative_to(root)) for p in (*files, *locks))
    git.run(root, "add", "--", config.changelog, *changed)
    title = f"chore(release): {version}"
    git.run(root, "commit", "--quiet", "-m", title)
    if push:
        git.run(root, "push", "--set-upstream", "origin", branch)
    if push and open_pr:
        _open_pr(config, branch, title, version, section)
    return version


def _open_pr(config: Config, branch: str, title: str, version: str, section: str) -> None:
    gh = shutil.which("gh")
    if gh is None:
        raise ReleaseError(f"pushed {branch}, but gh is not installed — open the PR by hand")
    body = (
        f"Release **{config.tag(version)}**. Squash-merge with the title as-is; CI tags the "
        f"merge commit and publishes the release.\n\n{section.split(chr(10), 1)[-1].strip()}\n"
    )
    proc = subprocess.run(
        [
            gh,
            "pr",
            "create",
            "--base",
            config.base_branch,
            "--head",
            branch,
            "--title",
            title,
            "--body",
            body,
        ],
        cwd=config.root,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise ReleaseError(f"gh pr create failed: {proc.stderr.strip()}")
    print(proc.stdout.strip())


@dataclass(frozen=True)
class Detection:
    released: bool
    version: str = ""
    tag: str = ""
    reason: str = ""

    def outputs(self) -> str:
        return f"released={str(self.released).lower()}\nversion={self.version}\ntag={self.tag}\n"


def detect(config: Config) -> Detection:
    """Is HEAD a release commit that still needs its tag?"""
    subject = _PR_SUFFIX.sub("", git.head_subject(config.root))
    m = RELEASE_SUBJECT.match(subject)
    if m is None:
        return Detection(False, reason="HEAD is not a chore(release) commit")
    version = m.group(1)
    if not semver.is_valid(version):
        raise ReleaseError(f"release commit names an invalid version: {version!r}")
    if config.version_source == "file":
        try:
            current = current_version(config)
        except ConfigError as e:
            raise ReleaseError(str(e)) from e
        if current != version:
            raise ReleaseError(f"release commit says {version}, the version files say {current}")
    tag = config.tag(version)
    if git.tag_exists(config.root, tag):
        tagged = git.run(config.root, "rev-list", "-n", "1", tag)
        if tagged != git.run(config.root, "rev-parse", "HEAD"):
            raise ReleaseError(f"{tag} already exists on another commit")
        return Detection(False, version, tag, reason=f"{tag} already tags HEAD")
    return Detection(True, version, tag)


def create_tag(config: Config, version: str, *, push: bool) -> str:
    tag = config.tag(version.removeprefix(config.tag_prefix))
    git.run(config.root, "tag", "-a", tag, "-m", tag)
    if push:
        git.run(config.root, "push", "origin", f"refs/tags/{tag}")
    return tag


def check_title(config: Config, title: str) -> list[str]:
    """Problems with a PR title / commit subject; empty when it is a valid conventional commit."""
    types = "|".join(re.escape(t.type) for t in config.types)
    m = re.match(
        r"^(?P<type>[A-Za-z]+)(\((?P<scope>[^()\s]+)\))?(?P<bang>!)?: (?P<subject>.*)$", title
    )
    if m is None:
        return [f'"{title}" is not "type(scope): subject" (scope optional, "!" marks breaking)']
    problems = []
    if not re.fullmatch(types, m["type"]):
        allowed = ", ".join(t.type for t in config.types)
        problems.append(f'unknown type "{m["type"]}" — allowed: {allowed}')
    subject = m["subject"]
    if not subject.strip() or subject != subject.strip():
        problems.append("the subject is empty or has leading/trailing whitespace")
    elif config.subject_lowercase and subject[0].isupper():
        problems.append(f'the subject should start lower-case: "{subject[0].lower()}{subject[1:]}"')
    return problems
