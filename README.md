# conventional-release

[![PyPI](https://img.shields.io/pypi/v/conventional-release)](https://pypi.org/project/conventional-release/)
[![Python](https://img.shields.io/pypi/pyversions/conventional-release)](https://pypi.org/project/conventional-release/)
[![CI](https://github.com/MdaaaaO/conventional-release/actions/workflows/ci.yml/badge.svg)](https://github.com/MdaaaaO/conventional-release/actions/workflows/ci.yml)
[![Coverage](https://raw.githubusercontent.com/MdaaaaO/conventional-release/python-coverage-comment-action-data/badge.svg)](https://github.com/MdaaaaO/conventional-release/tree/python-coverage-comment-action-data)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

A `CHANGELOG.md` in [standard-version](https://github.com/conventional-changelog/standard-version)'s
exact format, generated from [Conventional Commits](https://www.conventionalcommits.org). Releases go
through a **pull request**, and **CI tags the merge commit**. This works on a protected `main`, needs
no Node, and bumps the version in any language's version file.

```console
$ uvx conventional-release release          # version inferred from the commits
release 1.3.0 -> 1.4.0
https://github.com/you/project/pull/57       # "chore(release): 1.4.0", squash-merge it
                                             # CI then tags v1.4.0 and publishes the release
```

## Why another one

standard-version is deprecated. Here is how it compares with the alternatives:

| | changelog format | release on a protected branch | needs |
|---|---|---|---|
| [commit-and-tag-version](https://github.com/absolute-version/commit-and-tag-version) | standard-version's (it is the maintained drop-in fork) | tags locally, then pushes the tag | Node |
| [release-please](https://github.com/googleapis/release-please) | its own | a bot keeps a rolling release PR open | GitHub App / Action |
| [git-cliff](https://git-cliff.org) | whatever you template | changelog only; no version files, no PR, no tag | — |
| **conventional-release** | standard-version's | you open the release PR when you want a release; CI tags on merge | Python ≥ 3.11 (git-cliff comes with it) |

**If you want a drop-in replacement for `npx standard-version` and have Node, use
commit-and-tag-version.** This project is for repos where `main` only accepts PRs, and for
ecosystems where adding Node just to write a changelog isn't worth it.

## How a release works

1. **Every PR title is a conventional commit** (`feat(cli): add --json`). A squash merge turns the
   title into the commit subject, and GitHub appends ` (#57)`. That subject becomes the changelog
   line, with the PR and commit linked. The `pr-title` workflow below enforces this.
2. **`conventional-release release`** creates `release/vX.Y.Z` from your HEAD. It adds the new
   section to `CHANGELOG.md`, bumps the version files, commits `chore(release): X.Y.Z`, pushes, and
   opens the PR. `--dry-run` prints the version and the section and changes nothing.
3. **You squash-merge the PR with its title unchanged.**
4. **CI (the `tag` workflow) sees the `chore(release): X.Y.Z` commit on `main`.** It checks that the
   version files agree with the subject, creates an annotated tag `vX.Y.Z` on *that* commit, and
   publishes a GitHub Release whose notes are the version's changelog section. Your own jobs
   (publish to PyPI or npm, build images) run after it in the same workflow.

The tag is never created on the release branch: after a squash merge, that commit never lands on `main`.
If the Release step fails after the tag was already pushed, re-running the `tag` workflow (same
commit) publishes the still-missing Release without re-tagging.

## Install

```console
uv tool install conventional-release     # or: pipx install conventional-release
uvx conventional-release --help          # or run it without installing
```

The command is `conventional-release`, with `crel` as a short alias.
[git-cliff](https://pypi.org/project/git-cliff/) is a dependency and ships as a wheel, so there's
nothing else to install. `gh` is needed only to open the PR (`--no-pr` skips it).

## Commands

| command | does |
|---|---|
| `init [--force]` | set a repo up: `.conventional-release.toml` (detected version files and base branch) and the two workflows below; keeps files that exist |
| `release [major\|minor\|patch\|X.Y.Z] [--dry-run] [--no-push] [--no-pr]` | the local half, above |
| `next [level\|X.Y.Z]` | print the version the next release would get |
| `current` | print the current version |
| `notes X.Y.Z` | print that version's CHANGELOG section (the release notes) |
| `check-title "<title>"` | validate a PR title / commit subject; exits 1 with the reason |
| `detect [--github-output]` | CI: is HEAD a release commit that still needs its tag? prints `released=`, `version=`, `tag=` |
| `tag X.Y.Z [--push]` | CI: create the annotated tag on HEAD |
| `publish-release X.Y.Z` | CI: publish the GitHub Release for X.Y.Z's tag if it doesn't have one yet (idempotent) |

**Version inference** follows SemVer: `feat` bumps minor, `fix` and everything else bump patch,
and a `!` or a `BREAKING CHANGE:` footer bumps major. `feat` and breaking changes bump minor and
major even before `1.0.0`.

## GitHub Actions

Both workflows are reusable. Call them from your repo; `conventional-release init` writes these two
callers for you:

```yaml
# .github/workflows/release.yml
name: release
on:
  push:
    branches: [main]
permissions:
  contents: write
jobs:
  tag:
    uses: MdaaaaO/conventional-release/.github/workflows/tag.yml@v0
  publish:                        # optional: your own release jobs
    needs: tag
    if: needs.tag.outputs.released == 'true'
    runs-on: ubuntu-latest
    environment: pypi
    permissions:
      id-token: write             # PyPI trusted publishing
    steps:
      - uses: actions/checkout@v7
        with:
          ref: ${{ needs.tag.outputs.tag }}
      - uses: astral-sh/setup-uv@v10.2.0
      - run: uv build
      - uses: pypa/gh-action-pypi-publish@release/v1
```

```yaml
# .github/workflows/pr-title.yml — make this check required on main
name: pr-title
on:
  pull_request:
    types: [opened, edited, synchronize, reopened]
jobs:
  pr-title:
    uses: MdaaaaO/conventional-release/.github/workflows/pr-title.yml@v0
```

**Why publishing runs in *your* workflow, after `tag`, and not on `on: push: tags`:** a tag pushed
with the workflow's `GITHUB_TOKEN` doesn't trigger other workflows, so a separate tag-triggered
workflow would never start. Also, PyPI trusted publishing checks which workflow file publishes,
and that must be yours.

Both workflows also take a `runs-on` input (default `'"ubuntu-latest"'`) if you run on self-hosted
runners:

```yaml
    with:
      runs-on: '["self-hosted", "linux"]'
```

## Configuration

Every key is optional. Put them in `.conventional-release.toml`, or in `[tool.conventional-release]`
in `pyproject.toml`:

```toml
version-source = "file"          # "file": bump version files; "tag": the git tag is the version
                                 # (hatch-vcs, setuptools-scm) and the release PR only changes the changelog
version-files = ["pyproject.toml"]   # default: first of pyproject.toml, package.json, Cargo.toml,
                                     # VERSION, version that has a static version
changelog = "CHANGELOG.md"
changelog-mode = "prepend"       # "prepend": insert the new section, keep everything below it
                                 # "regenerate": rewrite the whole file from git history
tag-prefix = "v"
base-branch = "main"
branch-prefix = "release/"
initial-version = "0.1.0"        # the first release, when there is no tag yet
subject-lowercase = true         # check-title: "feat: add x", not "feat: Add x"
# repo-url = "https://github.com/o/r"   # default: derived from the origin remote
# cliff-config = "cliff.toml"           # use your own git-cliff config verbatim instead

# Types and their changelog sections, in display order. Default: the Angular set below.
[[types]]            # in pyproject.toml: [[tool.conventional-release.types]]
type = "feat"
section = "Features"
[[types]]
type = "fix"
section = "Bug Fixes"
[[types]]
type = "chore"
section = "Chore"
hidden = true        # still a valid title, just not listed in the changelog
```

The default types are `feat fix docs style refactor perf test build ci chore revert`, all listed.
`chore(release)` commits are never listed.

Version files are edited in place, one line each, and nothing else in the file changes. The
supported files are `pyproject.toml` (`[project]` or `[tool.poetry]`), `Cargo.toml` (`[package]`
or `[workspace.package]`), any `*.json` with a top-level `"version"` (`package.json`), and plain
one-line files (`VERSION`). Lock files next to a version file get the project's own version
bumped to match, so `uv run --locked`, `cargo build --locked` and `npm ci` keep working on the
release branch: `uv.lock` (next to `pyproject.toml`), `Cargo.lock` (next to `Cargo.toml`), and
`package-lock.json` or `npm-shrinkwrap.json` (next to `package.json`: the top-level `version` and
`packages[""]`). Other lock files are not touched.

**Coming from standard-version?** Keep your `CHANGELOG.md`. The default `prepend` mode adds new
sections above the old ones in the same format. Map your `.versionrc` `types` to `[[types]]`, and
your `bumpFiles` to `version-files`.

## Commit convention

Only [Conventional Commits 1.0](https://www.conventionalcommits.org/en/v1.0.0/) is supported. It
grew out of the Angular convention and is what git-cliff, release-please, semantic-release and
commitlint all use by default. This project's own history follows it, and the project releases
itself with itself.

## Lineage

This was extracted from the release tooling of a private project, which reproduced the
standard-version changelog of [atlassian-labs/observe](https://github.com/atlassian-labs/observe)
on git-cliff after standard-version was deprecated.

## License

[Apache-2.0](LICENSE)
