"""Resolve the running build's version string.

Rendered in the dashboard footer, e.g. "1.0.0 (45c4f05)" on a tagged build or
"1.0.0+3 (45c4f05)" three commits past the tag — the commit count doubles as a
monotonic build number, so we don't have to bump anything by hand.

Resolution order:
1. TILT_VERSION env var — a preformatted override (escape hatch).
2. TILT_GIT_DESCRIBE env var — the raw `git describe` baked at image build
   time, since `.git` isn't shipped inside the Docker image.
3. `git describe` run against the checkout (covers dev runs from the repo).
4. "unknown" if none of the above are available.
"""
import os
import re
import subprocess
from functools import lru_cache

# app/version.py -> repo root is one level up from the package dir.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@lru_cache(maxsize=1)
def get_version() -> str:
    override = os.environ.get("TILT_VERSION")
    if override:
        return override

    described = os.environ.get("TILT_GIT_DESCRIBE") or _git_describe()
    if described:
        return _format(described)

    return "unknown"


def _git_describe() -> str | None:
    try:
        out = subprocess.run(
            ["git", "describe", "--tags", "--always", "--long", "--dirty"],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip() or None


def _format(described: str) -> str:
    """Turn raw `git describe --long` output into a display string.

    Examples: "1.0.0-3-g45c4f05" -> "1.0.0+3 (45c4f05)",
              "1.0.0-0-g45c4f05" -> "1.0.0 (45c4f05)",
              "45c4f05" (no tag) -> "untagged (45c4f05)".
    """
    suffix = ""
    if described.endswith("-dirty"):
        described = described[: -len("-dirty")]
        suffix = "-dirty"

    m = re.match(r"^(?P<tag>.+)-(?P<count>\d+)-g(?P<commit>[0-9a-f]+)$", described)
    if not m:
        # No tag was reachable; git handed us a bare abbreviated commit.
        return f"untagged ({described}){suffix}"

    build = f"+{m['count']}" if int(m["count"]) else ""
    return f"{m['tag']}{build} ({m['commit']}){suffix}"
