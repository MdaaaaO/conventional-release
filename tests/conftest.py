from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


Commit = Callable[..., str]


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """An empty repo on `main` with a GitHub origin and a bare remote to push to."""
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.name", "Test")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "commit.gpgsign", "false")
    git(root, "config", "tag.gpgsign", "false")
    bare = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", str(bare))
    git(root, "remote", "add", "origin", str(bare))
    return root


@pytest.fixture
def commit(repo: Path) -> Commit:
    counter = iter(range(10_000))

    def make(message: str, **files: str) -> str:
        if not files:
            files = {f"file{next(counter)}.txt": "x"}
        for name, content in files.items():
            path = repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", message)
        return git(repo, "rev-parse", "HEAD")

    return make
