from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from conventional_release import cliff, release
from conventional_release.cli import main
from conventional_release.config import CommitType, Config, ConfigError, load
from conventional_release.git import web_url
from tests.conftest import Commit, git

TODAY = dt.date.today().isoformat()
URL = "https://github.com/o/r"


def _config(repo: Path, **kwargs: object) -> Config:
    return Config(root=repo, repo_url=URL, **kwargs)  # type: ignore[arg-type]


@pytest.fixture
def released(repo: Path, commit: Commit) -> Path:
    """A project at v1.0.0 (VERSION file + tag) with a CHANGELOG from before."""
    commit(
        "chore: start",
        VERSION="1.0.0\n",
        **{"CHANGELOG.md": cliff.HEADER + "## 1.0.0 (2020-01-01)\n\n\n### Features\n\n* old\n"},
    )
    git(repo, "tag", "-a", "v1.0.0", "-m", "v1.0.0")
    return repo


def test_standard_version_shape(released: Path, commit: Commit) -> None:
    feat = commit("feat(cli): add json output (#3)\n\nThe PR body.\nMore (#9) text.")
    fix = commit("fix: handle an empty repo (#4)")
    commit("not conventional")
    commit("chore(release): 0.9.0")
    config = _config(released)

    assert release.next_version(config) == "1.1.0"
    section = cliff.unreleased_section(config, "1.1.0")
    assert section == (
        f"## 1.1.0 ({TODAY})\n\n\n"
        "### Features\n\n"
        f"* **cli:** add json output ([#3]({URL}/issues/3)) "
        f"([{feat[:7]}]({URL}/commit/{feat}))\n\n\n"
        "### Bug Fixes\n\n"
        f"* handle an empty repo ([#4]({URL}/issues/4)) ([{fix[:7]}]({URL}/commit/{fix}))"
    )


def test_breaking_changes_section_and_major_bump(released: Path, commit: Commit) -> None:
    commit("refactor(api)!: rename the client\n\nBREAKING CHANGE: Client is now Session.")
    commit("feat!: drop python 3.10")
    config = _config(released)
    assert release.next_version(config) == "2.0.0"
    section = cliff.unreleased_section(config, "2.0.0")
    breaking = section.split("### ⚠ BREAKING CHANGES\n\n")[1].split("\n\n\n")[0]
    assert breaking == "* **api:** Client is now Session.\n* drop python 3.10"


def test_type_sections_follow_config_order_and_hidden(released: Path, commit: Commit) -> None:
    commit("fix: b")
    commit("chore: tidy")
    commit("feat: a")
    config = _config(
        released,
        types=(
            CommitType("fix", "Fixed"),
            CommitType("feat", "Added"),
            CommitType("chore", "Chore", hidden=True),
        ),
    )
    section = cliff.unreleased_section(config, "1.1.0")
    assert section.index("### Fixed") < section.index("### Added")
    assert "tidy" not in section


def test_no_repo_url_means_no_links(released: Path, commit: Commit) -> None:
    commit("fix: plain (#4)")
    config = Config(root=released)  # origin is a local path, so no web URL
    assert cliff.unreleased_section(config, "1.0.1").endswith("* plain (#4)")


def test_cut_prepends_bumps_commits_and_pushes(released: Path, commit: Commit) -> None:
    commit("feat: new thing")
    config = _config(released)
    assert release.cut(config, None, open_pr=False) == "1.1.0"

    assert git(released, "rev-parse", "--abbrev-ref", "HEAD") == "release/v1.1.0"
    assert git(released, "log", "-1", "--pretty=%s") == "chore(release): 1.1.0"
    assert git(released, "status", "--porcelain") == ""
    assert (released / "VERSION").read_text() == "1.1.0\n"
    changelog = (released / "CHANGELOG.md").read_text()
    assert changelog.startswith(cliff.HEADER + f"## 1.1.0 ({TODAY})")
    assert changelog.index("new thing") < changelog.index("## 1.0.0 (2020-01-01)")
    assert changelog.endswith(
        "* new thing (["
        + git(released, "rev-parse", "HEAD~1")[:7]
        + f"]({URL}/commit/{git(released, 'rev-parse', 'HEAD~1')}))\n\n"
        "## 1.0.0 (2020-01-01)\n\n\n### Features\n\n* old\n"
    )
    assert git(released, "ls-remote", "--heads", "origin", "release/v1.1.0")
    assert release.notes(config, "1.1.0").startswith("### Features\n\n* new thing")


def test_first_release_uses_the_version_already_in_the_file(repo: Path, commit: Commit) -> None:
    commit("feat: initial import", **{"pyproject.toml": '[project]\nversion = "0.1.0"\n'})
    config = _config(repo)
    assert release.plan(config) == ("0.1.0", "0.1.0")
    release.cut(config, None, push=False)
    assert (repo / "CHANGELOG.md").read_text().startswith(cliff.HEADER + "## 0.1.0 (")


def test_nothing_to_release(released: Path) -> None:
    with pytest.raises(release.ReleaseError, match="nothing to release"):
        release.plan(_config(released))


def test_dirty_tree_is_refused(released: Path, commit: Commit) -> None:
    commit("fix: x")
    (released / "stray.txt").write_text("x")
    with pytest.raises(release.ReleaseError, match="dirty"):
        release.cut(_config(released), None, push=False)


def test_forced_level_and_explicit_version(released: Path, commit: Commit) -> None:
    commit("fix: x")
    config = _config(released)
    assert release.next_version(config, "minor") == "1.1.0"
    assert release.next_version(config, "v3.0.0") == "3.0.0"
    with pytest.raises(release.ReleaseError):
        release.next_version(config, "bigger")


def test_regenerate_mode_rewrites_from_history(released: Path, commit: Commit) -> None:
    commit("feat: new")
    config = _config(released, changelog_mode="regenerate")
    release.cut(config, None, push=False)
    changelog = (released / "CHANGELOG.md").read_text()
    assert "* old" not in changelog  # the hand-written 1.0.0 section had no commits behind it
    assert changelog.startswith(cliff.HEADER + "## 1.1.0")


def test_tag_mode_leaves_files_alone(repo: Path, commit: Commit) -> None:
    commit("feat: a", **{"pyproject.toml": '[project]\ndynamic = ["version"]\n'})
    git(repo, "tag", "-a", "v0.3.0", "-m", "v0.3.0")
    commit("fix: b")
    config = _config(repo, version_source="tag")
    assert release.current_version(config) == "0.3.0"
    release.cut(config, None, push=False)
    assert git(repo, "show", "--name-only", "--pretty=", "HEAD") == "CHANGELOG.md"


def test_detect_and_tag_after_squash_merge(released: Path, commit: Commit) -> None:
    config = _config(released)
    assert not release.detect(config).released

    commit("chore(release): 1.1.0 (#12)\n\nRelease body", VERSION="1.1.0\n")
    found = release.detect(config)
    assert (found.released, found.version, found.tag) == (True, "1.1.0", "v1.1.0")

    release.create_tag(config, "1.1.0", push=True)
    assert git(released, "ls-remote", "--tags", "origin", "v1.1.0")
    again = release.detect(config)
    assert not again.released and "already tags HEAD" in again.reason


def test_detect_refuses_a_mismatched_version_file(released: Path, commit: Commit) -> None:
    commit("chore(release): 1.2.0")
    with pytest.raises(release.ReleaseError, match="version files say 1.0.0"):
        release.detect(_config(released))


@pytest.mark.parametrize(
    ("title", "ok"),
    [
        ("feat: add x", True),
        ("fix(cli)!: drop y", True),
        ("chore(release): 1.0.0", True),
        ("Feat: add x", False),
        ("feat: Add x", False),
        ("feature: x", False),
        ("feat:x", False),
        ("feat:  x", False),
        ("feat(): x", False),
    ],
)
def test_check_title(repo: Path, title: str, ok: bool) -> None:
    assert (release.check_title(Config(root=repo), title) == []) is ok


def test_config_from_pyproject_and_validation(repo: Path) -> None:
    (repo / "pyproject.toml").write_text(
        '[tool.conventional-release]\ntag-prefix = ""\nchangelog-mode = "regenerate"\n'
        '[[tool.conventional-release.types]]\ntype = "feat"\nsection = "New"\n'
    )
    config = load(repo)
    assert config.tag("1.0.0") == "1.0.0"
    assert config.types == (CommitType("feat", "New"),)

    (repo / ".conventional-release.toml").write_text('version-source = "magic"\n')
    with pytest.raises(ConfigError, match="version-source"):
        load(repo)
    (repo / ".conventional-release.toml").write_text("typo = 1\n")
    with pytest.raises(ConfigError, match="unknown key"):
        load(repo)


@pytest.mark.parametrize(
    ("remote", "url"),
    [
        ("git@github.com:o/r.git", URL),
        ("https://x-token@github.com/o/r.git", URL),
        ("ssh://git@gitlab.com/g/sub/r.git", "https://gitlab.com/g/sub/r"),
        ("/tmp/r.git", None),
    ],
)
def test_web_url(remote: str, url: str | None) -> None:
    assert web_url(remote) == url


def test_cli(released: Path, commit: Commit, capsys: pytest.CaptureFixture[str]) -> None:
    commit("fix: x")
    assert main(["-C", str(released), "next"]) == 0
    assert main(["-C", str(released), "current"]) == 0
    assert main(["-C", str(released), "check-title", "Nope"]) == 1
    assert main(["-C", str(released), "release", "--dry-run"]) == 0
    assert main(["-C", str(released), "notes", "9.9.9"]) == 1
    out, err = capsys.readouterr()
    assert out.startswith("1.0.1\n1.0.0\n## 1.0.1 (")
    assert "release 1.0.0 -> 1.0.1" in err and "no section for 9.9.9" in err


def test_prepend_without_earlier_releases(tmp_path: Path) -> None:
    fresh = tmp_path / "NEW.md"
    release.prepend(fresh, "## 0.1.0 (d)\n\n* a\n")
    assert fresh.read_text() == cliff.HEADER + "## 0.1.0 (d)\n\n* a\n"

    notes_only = tmp_path / "CHANGELOG.md"
    notes_only.write_text("# Changelog\n\nSome intro.")
    release.prepend(notes_only, "## 0.1.0 (d)\n")
    assert notes_only.read_text() == "# Changelog\n\nSome intro.\n\n## 0.1.0 (d)\n"
