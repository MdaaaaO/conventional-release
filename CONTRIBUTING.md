# Contributing

Thanks for helping. The short version:

- **Open an issue first** for anything bigger than a typo, so we agree on the change before you write it.
- **PR titles are [Conventional Commits](https://www.conventionalcommits.org).** PRs are
  squash-merged, the title becomes the commit, and the commit becomes the changelog line. The
  `pr-title` check enforces this (`feat(cli): add --json`, `fix: …`, `docs: …`). Put `!` after
  the type or scope for a breaking change, and explain it in a `BREAKING CHANGE:` footer in the
  PR description.
- **`make ci` passes locally** before you push. It runs ruff, `mypy --strict`, pytest with branch
  coverage, and actionlint. You need [uv](https://docs.astral.sh/uv/). Run `make install` once.
- New behaviour comes with a test. The tests build throwaway git repos in `tmp_path`; see
  `tests/conftest.py`.

## Releasing (maintainers)

`make release` (or `make release ARGS=minor`) opens the `chore(release): X.Y.Z` PR. Squash-merge
it with the title unchanged. `release.yml` then tags the merge commit, publishes the GitHub
Release, publishes to TestPyPI and then to PyPI (the `pypi` environment waits for approval), and
moves the `v0` major tag. `make release-dry` shows what would ship.
