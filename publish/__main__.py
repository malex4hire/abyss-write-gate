"""`python3 -m publish`: verify the published surface, anonymously.

No arguments, no credentials, re-runnable. The published surface can break
after the fact (a renamed file, a moved artifact, a rewritten README), so this
is a command rather than a checklist someone performed once.
"""

from __future__ import annotations

import sys
from pathlib import Path

from . import surface
from .surface import FAIL, UNAVAILABLE, UrllibFetcher

REPO_ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None, fetcher=None, root=None) -> int:
    root = Path(root) if root else REPO_ROOT
    owner, name = surface.repo_slug(root)
    branch = surface.current_branch(root)
    fetcher = fetcher or UrllibFetcher()

    print()
    print("  abyss-write-gate: published surface, fetched anonymously")
    print(f"  {owner}/{name} @ {branch}")
    print("  " + "-" * 68)

    results = surface.run_all(fetcher, owner, name, branch, root)
    for result in results:
        print(f"  {result.status:<12} {result.name:<12} {result.detail}")

    failed = [r for r in results if r.status == FAIL]
    missing = [r for r in results if r.status == UNAVAILABLE]
    print("  " + "-" * 68)
    if not failed and not missing:
        print(f"  VERIFIED. {len(results)} checks passed against the public URL.")
        print()
        return 0
    if failed:
        print(f"  NOT VERIFIED. {len(failed)} check(s) found the property violated.")
    if missing:
        print(
            f"  NOT VERIFIED. {len(missing)} check(s) could not obtain evidence; "
            "unknown is not a pass."
        )
    print()
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
