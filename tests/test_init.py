"""`init`: the config and the two caller workflows."""

from __future__ import annotations

from pathlib import Path

import pytest

from conventional_release import release, scaffold
from conventional_release.cli import main
from conventional_release.config import load
from tests.conftest import Commit, git


def test_init_writes_config_and_workflows(
    repo: Path, commit: Commit, capsys: pytest.CaptureFixture[str]
) -> None:
    commit("chore: start", **{"pyproject.toml": '[project]\nname = "x"\nversion = "0.3.0"\n'})
    assert main(["-C", str(repo), "init"]) == 0
    out, err = capsys.readouterr()
    assert out.splitlines() == [
        "wrote .github/workflows/release.yml",
        "wrote .github/workflows/pr-title.yml",
        "wrote .conventional-release.toml",
    ]
    assert "required on main" in err

    config = load(repo)
    assert config.version_files == ("pyproject.toml",)
    assert release.current_version(config) == "0.3.0"
    workflow = (repo / ".github/workflows/release.yml").read_text()
    assert "branches: [main]" in workflow
    assert f"uses: {scaffold.REUSABLE}/tag.yml@v0" in workflow
    assert "${{ needs.tag.outputs.tag }}" in workflow  # GitHub expressions survive the templating
    pr_title = (repo / ".github/workflows/pr-title.yml").read_text()
    assert f"uses: {scaffold.REUSABLE}/pr-title.yml@v0" in pr_title


def test_init_keeps_what_exists_unless_forced(repo: Path, commit: Commit) -> None:
    commit("chore: start", VERSION="1.0.0\n", **{".github/workflows/release.yml": "mine\n"})
    assert scaffold.init(repo) == [
        (".github/workflows/release.yml", False),
        (".github/workflows/pr-title.yml", True),
        (".conventional-release.toml", True),
    ]
    assert (repo / ".github/workflows/release.yml").read_text() == "mine\n"
    (repo / ".conventional-release.toml").write_text('base-branch = "develop"\n')
    # An existing config is never rewritten, even forced, and gives the workflows their branch.
    assert scaffold.init(repo, force=True)[0] == (".conventional-release.toml", False)
    assert "branches: [develop]" in (repo / ".github/workflows/release.yml").read_text()
    assert (repo / ".conventional-release.toml").read_text() == 'base-branch = "develop"\n'


def test_init_respects_pyproject_config(repo: Path) -> None:
    (repo / "pyproject.toml").write_text(
        '[project]\nversion = "1.0.0"\n\n[tool.conventional-release]\nbase-branch = "trunk"\n'
    )
    assert scaffold.init(repo)[0] == ("pyproject.toml", False)
    assert not (repo / ".conventional-release.toml").exists()
    assert "branches: [trunk]" in (repo / ".github/workflows/release.yml").read_text()
    (repo / "pyproject.toml").write_text('[project]\nversion = "1.0.0"\n')
    assert scaffold.configured_in(repo) is None


def test_no_version_file_means_tag_mode(repo: Path) -> None:
    (repo / "pyproject.toml").write_text('[project]\ndynamic = ["version"]\n')
    text = scaffold.config_text(repo, "main")
    assert 'version-source = "tag"' in text and "version-files" not in text


def test_default_branch(repo: Path, commit: Commit, tmp_path: Path) -> None:
    assert scaffold.default_branch(repo) == "main"  # the checked-out branch, even before a commit
    commit("chore: start")
    git(repo, "push", "-q", "origin", "main")
    git(repo, "remote", "set-head", "origin", "main")
    git(repo, "checkout", "-q", "-b", "feature")
    assert scaffold.default_branch(repo) == "main"  # origin's HEAD wins over the checkout
    git(repo, "checkout", "-q", "--detach")
    git(repo, "remote", "set-head", "origin", "--delete")
    assert scaffold.default_branch(repo) == "main"  # nothing to go on: the fallback
    not_a_repo = tmp_path / "plain"
    not_a_repo.mkdir()
    assert scaffold.default_branch(not_a_repo) == "main"
