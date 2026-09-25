"""The paths around the core: opening the PR, CI's detect/tag, config and version-file errors."""

from __future__ import annotations

import runpy
import stat
from pathlib import Path

import pytest

from conventional_release import cliff, release
from conventional_release.cli import main
from conventional_release.config import Config, ConfigError, load, version_files
from tests.conftest import Commit, git

URL = "https://github.com/o/r"


@pytest.fixture
def released(repo: Path, commit: Commit) -> Path:
    commit("chore: start", VERSION="1.0.0\n")
    git(repo, "tag", "-a", "v1.0.0", "-m", "v1.0.0")
    return repo


@pytest.fixture
def fake_gh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A `gh` on PATH that logs each call's args (calls separated by `===CALL===` lines).

    `pr create` and `release create` fail when $FAKE_GH_EXIT is set. `release view` succeeds
    only when $FAKE_GH_RELEASE_EXISTS=1; otherwise it fails with $FAKE_GH_VIEW_STDERR (default
    "release not found", gh's real message for a tag with no Release).
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "gh.log"
    gh = bin_dir / "gh"
    gh.write_text(
        "#!/bin/sh\n"
        f'{{ printf "%s\\n" "$@"; printf -- "===CALL===\\n"; }} >> "{log}"\n'
        'if [ "$1 $2" = "release view" ]; then\n'
        '  if [ "${FAKE_GH_RELEASE_EXISTS:-0}" = "1" ]; then\n'
        '    echo "https://github.com/o/r/releases/tag/$3"; exit 0\n'
        "  fi\n"
        '  echo "${FAKE_GH_VIEW_STDERR:-release not found}" >&2\n'
        "  exit 1\n"
        "fi\n"
        'if [ "${FAKE_GH_EXIT:-0}" != 0 ]; then echo "gh: boom" >&2; exit "$FAKE_GH_EXIT"; fi\n'
        'if [ "$1 $2" = "release create" ]; then echo "https://github.com/o/r/releases/tag/$3"\n'
        "else echo https://github.com/o/r/pull/7\n"
        "fi\n"
    )
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bin_dir}:{Path('/usr/bin')}:{Path('/bin')}")
    return log


def test_cut_opens_the_pr(
    released: Path, commit: Commit, fake_gh: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    commit("feat: a thing")
    release.cut(Config(root=released, repo_url=URL), None)
    args = fake_gh.read_text().splitlines()
    assert args[:2] == ["pr", "create"]
    assert args[args.index("--title") + 1] == "chore(release): 1.1.0"
    assert args[args.index("--head") + 1] == "release/v1.1.0"
    assert args[args.index("--base") + 1] == "main"
    body = "\n".join(args[args.index("--body") + 1 :])
    assert body.startswith("Release **v1.1.0**") and "### Features" in body
    assert capsys.readouterr().out.strip() == "https://github.com/o/r/pull/7"


def test_gh_failure_is_reported(
    released: Path, commit: Commit, fake_gh: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    commit("fix: x")
    monkeypatch.setenv("FAKE_GH_EXIT", "1")
    with pytest.raises(release.ReleaseError, match="gh pr create failed: gh: boom"):
        release.cut(Config(root=released), None)


def test_missing_gh_is_reported(
    released: Path, commit: Commit, monkeypatch: pytest.MonkeyPatch
) -> None:
    commit("fix: x")
    monkeypatch.setattr("shutil.which", lambda _: None)
    with pytest.raises(release.ReleaseError, match="gh is not installed"):
        release.cut(Config(root=released), None)


def _tagged_release(released: Path, commit: Commit, version: str, notes: str) -> Config:
    changelog = cliff.HEADER + f"## {version} (2020-01-01)\n\n\n### Features\n\n{notes}\n"
    commit(f"chore(release): {version}", VERSION=f"{version}\n", **{"CHANGELOG.md": changelog})
    config = Config(root=released)
    release.create_tag(config, version, push=False)
    return config


def test_publish_release_creates_the_missing_release(
    released: Path, commit: Commit, fake_gh: Path
) -> None:
    config = _tagged_release(released, commit, "1.1.0", "* a")
    assert release.publish_release(config, "1.1.0") is True
    calls = [c.splitlines() for c in fake_gh.read_text().split("===CALL===\n") if c]
    assert calls[0] == ["release", "view", "v1.1.0"]
    assert calls[1][:5] == ["release", "create", "v1.1.0", "--title", "v1.1.0"]
    assert "--notes" in calls[1] and "* a" in calls[1] and "--verify-tag" in calls[1]


def test_publish_release_is_idempotent_when_already_published(
    released: Path, commit: Commit, fake_gh: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _tagged_release(released, commit, "1.1.0", "* a")
    monkeypatch.setenv("FAKE_GH_RELEASE_EXISTS", "1")
    assert release.publish_release(config, "1.1.0") is False
    assert "release create" not in fake_gh.read_text()


def test_publish_release_never_treats_a_real_gh_error_as_missing(
    released: Path, commit: Commit, fake_gh: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _tagged_release(released, commit, "1.1.0", "* a")
    monkeypatch.setenv("FAKE_GH_VIEW_STDERR", "gh: authentication failed")
    with pytest.raises(
        release.ReleaseError, match="gh release view v1.1.0 failed: gh: authentication failed"
    ):
        release.publish_release(config, "1.1.0")
    assert "release create" not in fake_gh.read_text()


def test_publish_release_reports_a_create_failure(
    released: Path, commit: Commit, fake_gh: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _tagged_release(released, commit, "1.1.0", "* a")
    monkeypatch.setenv("FAKE_GH_EXIT", "1")
    with pytest.raises(release.ReleaseError, match="gh release create failed: gh: boom"):
        release.publish_release(config, "1.1.0")


def test_publish_release_missing_gh_is_reported(
    released: Path, commit: Commit, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _tagged_release(released, commit, "1.1.0", "* a")
    monkeypatch.setattr("shutil.which", lambda _: None)
    with pytest.raises(release.ReleaseError, match="gh is not installed"):
        release.publish_release(config, "1.1.0")


def test_cli_release_paths(
    released: Path, commit: Commit, capsys: pytest.CaptureFixture[str]
) -> None:
    commit("fix: x")
    assert main(["-C", str(released), "release", "--no-push"]) == 0
    assert 'open a PR titled "chore(release): 1.0.1"' in capsys.readouterr().err

    git(released, "checkout", "-q", "main")
    commit("fix: y")
    git(released, "branch", "-D", "release/v1.0.1")
    assert main(["-C", str(released), "release", "--no-pr"]) == 0
    assert "CI tags the merge commit" in capsys.readouterr().err
    assert git(released, "ls-remote", "--heads", "origin", "release/v1.0.1")


def test_cli_detect_and_tag_for_ci(
    released: Path,
    commit: Commit,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    out_file = tmp_path / "github_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))
    commit("docs: not a release")
    assert main(["-C", str(released), "detect", "--github-output"]) == 0
    assert "released=false" in out_file.read_text()
    assert "not a chore(release) commit" in capsys.readouterr().err

    commit("chore(release): 1.0.1 (#5)", VERSION="1.0.1\n")
    assert main(["-C", str(released), "detect", "--github-output"]) == 0
    assert out_file.read_text().endswith("released=true\nversion=1.0.1\ntag=v1.0.1\n")
    assert main(["-C", str(released), "tag", "v1.0.1", "--push"]) == 0
    assert capsys.readouterr().out.endswith("v1.0.1\n")
    assert git(released, "ls-remote", "--tags", "origin", "v1.0.1")


def test_cli_publish_release_repairs_a_rerun_after_a_failed_release_step(
    released: Path,
    commit: Commit,
    fake_gh: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`tag.yml`'s scenario: the tag got pushed, then the "GitHub Release" step failed, so a
    re-run of the same job sees `released=false` but must still publish the Release."""
    commit(
        "chore(release): 1.1.0",
        VERSION="1.1.0\n",
        **{"CHANGELOG.md": cliff.HEADER + "## 1.1.0 (2020-01-01)\n\n\n### Features\n\n* a\n"},
    )
    out_file = tmp_path / "github_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))
    assert main(["-C", str(released), "detect", "--github-output"]) == 0
    assert out_file.read_text() == "released=true\nversion=1.1.0\ntag=v1.1.0\n"
    assert main(["-C", str(released), "tag", "1.1.0", "--push"]) == 0
    # ...the real workflow's "GitHub Release" step fails here (network/token/notes error).

    out_file.write_text("")  # a re-run of the job gets a fresh $GITHUB_OUTPUT
    assert main(["-C", str(released), "detect", "--github-output"]) == 0
    assert out_file.read_text() == "released=false\nversion=1.1.0\ntag=v1.1.0\n"

    assert main(["-C", str(released), "publish-release", "1.1.0"]) == 0
    assert "published" in capsys.readouterr().err
    calls = [c.splitlines() for c in fake_gh.read_text().split("===CALL===\n") if c]
    assert calls[-2] == ["release", "view", "v1.1.0"]
    assert calls[-1][:3] == ["release", "create", "v1.1.0"]


def test_detect_edge_cases(released: Path, commit: Commit) -> None:
    commit("chore(release): 01.0.0")
    with pytest.raises(release.ReleaseError, match="invalid version"):
        release.detect(Config(root=released))

    commit("chore(release): 1.0.0")  # v1.0.0 exists, but on an older commit
    with pytest.raises(release.ReleaseError, match="already exists on another commit"):
        release.detect(Config(root=released))

    commit("chore(release): 2.0.0")
    tag_mode = Config(root=released, version_source="tag")
    assert release.detect(tag_mode).released  # tag mode has no files to cross-check


def test_version_file_problems(repo: Path, commit: Commit) -> None:
    commit("feat: a", VERSION="1.0.0\n", **{"package.json": '{"version": "2.0.0"}\n'})
    config = Config(root=repo, version_files=("VERSION", "package.json"))
    with pytest.raises(release.ReleaseError, match="version files disagree"):
        release.current_version(config)
    with pytest.raises(ConfigError, match="not found: nope.txt"):
        version_files(Config(root=repo, version_files=("nope.txt",)))
    (repo / "VERSION").unlink()
    (repo / "package.json").unlink()
    with pytest.raises(ConfigError, match="no version file found"):
        version_files(Config(root=repo))
    commit("chore(release): 1.0.0")
    with pytest.raises(release.ReleaseError, match="no version file found"):
        release.detect(Config(root=repo))


@pytest.mark.parametrize(
    ("toml", "error"),
    [
        ("tag-prefix = 1\n", "tag-prefix must be a str"),
        ('version-files = "VERSION"\n', "version-files must be a list"),
        ('changelog-mode = "rewrite"\n', "changelog-mode must be one of"),
        ("types = []\n", "types must be a non-empty array"),
        ("[[types]]\nsection = 'x'\n", "needs a string 'type'"),
        ("[[types]]\ntype = 'feat'\nhidden = 'yes'\n", "section is a string, hidden a bool"),
    ],
)
def test_config_errors(repo: Path, toml: str, error: str) -> None:
    (repo / ".conventional-release.toml").write_text(toml)
    with pytest.raises(ConfigError, match=error):
        load(repo)


def test_cli_reports_expected_errors(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (repo / ".conventional-release.toml").write_text("typo = 1\n")
    assert main(["-C", str(repo), "current"]) == 1
    assert capsys.readouterr().err.startswith("error: ")


def test_python_dash_m(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr("sys.argv", ["conventional-release", "--version"])
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module("conventional_release", run_name="__main__")
    assert exit_info.value.code == 0
    assert capsys.readouterr().out.startswith("conventional-release ")


def test_git_cliff_lookup_falls_back_to_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("sys.executable", str(tmp_path / "python"))
    monkeypatch.setattr("shutil.which", lambda _: "/opt/bin/git-cliff")
    assert cliff.binary() == "/opt/bin/git-cliff"
    monkeypatch.setattr("shutil.which", lambda _: None)
    with pytest.raises(cliff.CliffError, match="git-cliff not found"):
        cliff.binary()


def test_git_cliff_failure_is_reported(released: Path, commit: Commit) -> None:
    commit("fix: x", **{"broken-cliff.toml": "[changelog\n"})
    config = Config(root=released, cliff_config="broken-cliff.toml")
    with pytest.raises(cliff.CliffError, match="failed"):
        cliff.unreleased_section(config, "1.0.1")
