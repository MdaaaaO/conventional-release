"""Command line: `conventional-release <command>` (alias `crel`)."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from conventional_release import __version__, cliff, release
from conventional_release.config import Config, ConfigError, load
from conventional_release.git import GitError
from conventional_release.versionfiles import VersionFileError

EXPECTED = (ConfigError, GitError, VersionFileError, cliff.CliffError, release.ReleaseError)


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="conventional-release",
        description="standard-version-style CHANGELOG and release PRs from Conventional Commits.",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument(
        "-C", dest="root", type=Path, default=Path.cwd(), help="run as if started in this directory"
    )
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("release", help="branch, CHANGELOG, version bump, commit, push, open a PR")
    r.add_argument(
        "bump", nargs="?", help="major | minor | patch | X.Y.Z (default: inferred from the commits)"
    )
    r.add_argument(
        "--dry-run",
        action="store_true",
        help="print the version and the changelog section, change nothing",
    )
    r.add_argument("--no-push", action="store_true", help="stop after the local commit")
    r.add_argument("--no-pr", action="store_true", help="push the branch but open no PR")

    sub.add_parser("current", help="print the current version")
    n = sub.add_parser("next", help="print the version the next release would get")
    n.add_argument("bump", nargs="?", help="major | minor | patch | X.Y.Z")

    no = sub.add_parser("notes", help="print one version's CHANGELOG section (release notes)")
    no.add_argument("version")

    d = sub.add_parser("detect", help="CI: is HEAD a release commit that still needs its tag?")
    d.add_argument(
        "--github-output",
        action="store_true",
        help="also append released/version/tag to $GITHUB_OUTPUT",
    )

    t = sub.add_parser("tag", help="CI: create the annotated tag for VERSION on HEAD")
    t.add_argument("version")
    t.add_argument("--push", action="store_true", help="push the tag to origin")

    c = sub.add_parser("check-title", help="validate a PR title / commit subject")
    c.add_argument("title")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        config = load(args.root.resolve())
        return _run(args, config)
    except EXPECTED as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


def _run(args: argparse.Namespace, config: Config) -> int:
    if args.command == "current":
        print(release.current_version(config) or "")
    elif args.command == "next":
        print(release.plan(config, args.bump)[1])
    elif args.command == "notes":
        print(release.notes(config, args.version), end="")
    elif args.command == "check-title":
        problems = release.check_title(config, args.title)
        for problem in problems:
            print(f"error: {problem}", file=sys.stderr)
        return 1 if problems else 0
    elif args.command == "detect":
        result = release.detect(config)
        print(result.outputs(), end="")
        if result.reason:
            print(result.reason, file=sys.stderr)
        if args.github_output:
            with open(os.environ["GITHUB_OUTPUT"], "a") as f:
                f.write(result.outputs())
    elif args.command == "tag":
        print(release.create_tag(config, args.version, push=args.push))
    elif args.command == "release":
        return _release(args, config)
    return 0


def _release(args: argparse.Namespace, config: Config) -> int:
    current, version = release.plan(config, args.bump)
    print(f"release {current or '(none)'} -> {version}", file=sys.stderr)
    if args.dry_run:
        print(
            f"(dry run — nothing written; branch would be {config.branch(version)})\n",
            file=sys.stderr,
        )
        print(cliff.unreleased_section(config, version))
        return 0
    release.cut(config, args.bump, push=not args.no_push, open_pr=not args.no_pr)
    if args.no_push:
        print(
            f"committed on {config.branch(version)}; push it and open a PR titled "
            f'"chore(release): {version}"',
            file=sys.stderr,
        )
    else:
        print(
            "Squash-merge the PR with its title as-is; CI tags the merge commit.", file=sys.stderr
        )
    return 0
