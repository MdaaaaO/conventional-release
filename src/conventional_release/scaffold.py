"""`init`: write the config and the two workflows that call the reusable ones.

Nothing that exists is overwritten unless asked (`force`), and an existing configuration, in
`.conventional-release.toml` or `[tool.conventional-release]`, is always left alone: it is the
source for the workflows' base branch instead.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from conventional_release import git
from conventional_release.config import CONFIG_FILE, Config, ConfigError, load, version_files

REUSABLE = "MdaaaaO/conventional-release/.github/workflows"
CONFIG_URL = "https://github.com/MdaaaaO/conventional-release#configuration"

RELEASE_WORKFLOW = """\
name: release

# On every push to @BASE@: when the pushed commit is a squash-merged `chore(release): X.Y.Z`,
# tag it vX.Y.Z and publish a GitHub Release with its CHANGELOG section.
on:
  push:
    branches: [@BASE@]

permissions:
  contents: write

jobs:
  tag:
    uses: @REUSABLE@/tag.yml@v0

  # Publish in this same workflow, after `tag`: a tag pushed with GITHUB_TOKEN starts no other
  # workflow, so `on: push: tags` would never fire.
  # publish:
  #   needs: tag
  #   if: needs.tag.outputs.released == 'true'
  #   runs-on: ubuntu-latest
  #   steps:
  #     - uses: actions/checkout@v7
  #       with:
  #         ref: ${{ needs.tag.outputs.tag }}
  #     - run: echo "build and publish ${{ needs.tag.outputs.version }} here"
"""

PR_TITLE_WORKFLOW = """\
name: pr-title

# PR titles become the squash commit and the CHANGELOG line, so they must be Conventional
# Commits. Make this check required on @BASE@.
on:
  pull_request:
    types: [opened, edited, synchronize, reopened]

jobs:
  pr-title:
    uses: @REUSABLE@/pr-title.yml@v0
"""


def default_branch(root: Path) -> str:
    """origin's default branch, else the checked-out branch, else `main`."""
    for args in (
        ("symbolic-ref", "--short", "refs/remotes/origin/HEAD"),
        ("branch", "--show-current"),
    ):
        try:
            name = git.run(root, *args)
        except git.GitError:
            continue
        if name:
            return name.removeprefix("origin/")
    return "main"


def config_text(root: Path, base: str) -> str:
    """A starter `.conventional-release.toml`: the detected version source, files and branch."""
    lines = [f"# conventional-release. Every key is optional: {CONFIG_URL}"]
    try:
        files = version_files(Config(root=root))
    except ConfigError:
        lines += [
            "# No file with a static version was found, so the git tag is the version",
            "# (hatch-vcs, setuptools-scm). The release PR then only changes the changelog.",
            'version-source = "tag"',
        ]
    else:
        listed = ", ".join(f'"{p.relative_to(root).as_posix()}"' for p in files)
        lines += ['version-source = "file"', f"version-files = [{listed}]"]
    lines.append(f'base-branch = "{base}"')
    return "\n".join(lines) + "\n"


def configured_in(root: Path) -> str | None:
    """Where the project's configuration lives, if it has one."""
    if (root / CONFIG_FILE).is_file():
        return CONFIG_FILE
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        with pyproject.open("rb") as f:
            if "conventional-release" in tomllib.load(f).get("tool", {}):
                return "pyproject.toml"
    return None


def init(root: Path, *, force: bool = False) -> list[tuple[str, bool]]:
    """Write what is missing; return (path, written) for every file init manages."""
    configured = configured_in(root)
    base = load(root).base_branch if configured else default_branch(root)
    files = {
        ".github/workflows/release.yml": RELEASE_WORKFLOW,
        ".github/workflows/pr-title.yml": PR_TITLE_WORKFLOW,
    }
    done = []
    if configured:
        done.append((configured, False))
    else:
        files[CONFIG_FILE] = config_text(root, base)
    for rel, text in files.items():
        path = root / rel
        if path.exists() and not force:
            done.append((rel, False))
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text.replace("@BASE@", base).replace("@REUSABLE@", REUSABLE))
        done.append((rel, True))
    return done
