"""standard-version-style CHANGELOG and release PRs from Conventional Commits."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("conventional-release")
except PackageNotFoundError:  # running from a source tree that was never installed
    __version__ = "0.0.0"
