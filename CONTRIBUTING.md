# Contributing

Thanks for helping. The short version:

- **Open an issue first** for anything bigger than a typo, so we agree on the change before you write it.
  The bug and feature forms ask for what a fix needs: the version, the command or workflow, and the
  commits that show the problem.
- **PR titles are [Conventional Commits](https://www.conventionalcommits.org).** PRs are
  squash-merged, the title becomes the commit, and the commit becomes the changelog line. The
  `pr-title` check enforces this (`feat(cli): add --json`, `fix: …`, `docs: …`). Put `!` after
  the type or scope for a breaking change, and explain it in a `BREAKING CHANGE:` footer in the
  PR description.
- **`make ci` passes locally** before you push. It runs ruff, `mypy --strict`, pytest with branch
  coverage (the floor is 95%), and actionlint. You need [uv](https://docs.astral.sh/uv/). Run `make install` once.
- New behaviour comes with a test. The tests build throwaway git repos in `tmp_path`; see
  `tests/conftest.py`.

## Code review

Every non-draft PR from a branch of this repo gets an automatic review by Claude
(`.github/workflows/claude-review.yml`). Findings land as inline comments plus one summary comment.
Maintainers can ask it anything with `@claude …` in a PR or issue comment, and ask for a fresh
review of the head after a fix push with `@claude review`.

- **The review is advisory, but its threads are not optional.** Every thread is answered and
  resolved before merge, in one of three ways:
  - fixed on the branch (the default), with a reply naming the commit;
  - deferred to an issue labelled `review-followup`, cited in the reply and picked up right after
    the merge;
  - disagreed with, with the reason in the reply.
  The `main` ruleset requires resolved threads, so GitHub enforces this.
- Release PRs (`chore(release): …`) and Dependabot PRs are not reviewed.
- Maintainer PRs link an issue with `Closes #N` or `Refs #N`. Release and Dependabot PRs are exempt.
- The `coverage` job comments the coverage of the change on the PR, and the badge in the README
  follows `main`. PRs from forks get no Claude review and no coverage comment, because GitHub gives
  them no secrets and a read-only token. A maintainer runs `@claude review` for them.
- Merging is squash-only, and the branch is deleted after merge.

## Releasing (maintainers)

`make release` (or `make release ARGS=minor`) opens the `chore(release): X.Y.Z` PR. Squash-merge
it with the title unchanged. `release.yml` then tags the merge commit, publishes the GitHub
Release, publishes to TestPyPI and then to PyPI (the `pypi` environment waits for approval), and
moves the `v0` major tag. `make release-dry` shows what would ship.
