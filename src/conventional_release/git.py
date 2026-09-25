"""Thin wrappers over the git CLI. Every call raises on a non-zero exit."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


class GitError(Exception):
    pass


def run(root: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    if proc.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc.stdout.strip()


def status_porcelain(root: Path) -> str:
    return run(root, "status", "--porcelain")


def latest_tag(root: Path, prefix: str) -> str | None:
    try:
        return run(root, "describe", "--tags", "--abbrev=0", "--match", f"{prefix}[0-9]*")
    except GitError:
        return None


def tag_exists(root: Path, tag: str) -> bool:
    try:
        run(root, "rev-parse", "--verify", "--quiet", f"refs/tags/{tag}")
    except GitError:
        return False
    return True


def branch_exists(root: Path, branch: str) -> bool:
    try:
        run(root, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}")
    except GitError:
        return False
    return True


def head_subject(root: Path) -> str:
    return run(root, "log", "-1", "--pretty=%s")


def remote_url(root: Path, remote: str = "origin") -> str | None:
    try:
        return run(root, "remote", "get-url", remote)
    except GitError:
        return None


_SSH = re.compile(r"^(?:ssh://)?git@([^:/]+)[:/](.+?)(?:\.git)?/?$")
_HTTPS = re.compile(r"^https?://(?:[^@/]+@)?([^/]+)/(.+?)(?:\.git)?/?$")


def web_url(remote: str) -> str | None:
    """git@github.com:o/r.git, https://x@github.com/o/r → https://github.com/o/r"""
    for pattern in (_SSH, _HTTPS):
        if m := pattern.match(remote):
            return f"https://{m.group(1)}/{m.group(2)}"
    return None
