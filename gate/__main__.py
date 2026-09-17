"""The single entry point.

    make demo          ->  python3 -m gate

Runs the whole adversarial set, writes the known-miss register and the README
artifact, and exits non-zero if any case reached a disposition other than the
one it declares. There are two outcomes and no third: verified, or fail.

No credential is read, no network call is made, and no model is contacted. The
hostile driver is deterministic, which is why a clean clone reproduces every
number in the published register.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import cast, register
from .register import money
from .runner import RunResult, execute_run

REPO_ROOT = Path(__file__).resolve().parent.parent


def _summarise(result: RunResult, artifacts: list[Path], stream) -> None:
    counts = result.counts()
    write = lambda text="": print(text, file=stream)  # noqa: E731

    write()
    write("  abyss-write-gate — adversarial run")
    write("  " + "-" * 56)
    for cls, runs in sorted(result.by_class().items()):
        caught = sum(1 for r in runs if r.disposition == "caught")
        missed = len(runs) - caught
        flag = f"{missed} missed" if missed else "all caught"
        noun = "case " if len(runs) == 1 else "cases"
        write(f"  {cls:<28} {len(runs):>2} {noun}   {flag}")
    write("  " + "-" * 56)
    write(f"  cases {counts['cases']}   caught {counts['caught']}   missed {counts['missed']}")
    write(f"  actions attempted against the gate: {counts['attempts']}")
    write(f"  forbidden mutations landed: {counts['forbidden_mutations_landed']}")
    write()
    for run in result.missed:
        write(f"  MISS  {run.case.id}  {run.case.miss_reason_class}")
        write(f"        {run.case.title}")
    write()
    for path in artifacts:
        write(f"  wrote {path}")
    write()
    if result.ok():
        write("  VERIFIED — every case reached the disposition it declares.")
    else:
        for case_id, expected, observed in result.unmet_expectations:
            write(f"  FAIL  {case_id}: expected {expected}, observed {observed}")
        for run in result.mismatches:
            write(
                f"  FAIL  {run.case.id}: declared {run.case.expected_disposition}, "
                f"observed {run.disposition}"
            )
    write()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m gate",
        description="Run the adversarial set and publish the results.",
    )
    parser.add_argument(
        "--run-dir",
        default=None,
        help="where the per-case datastores are written (default: out/run)",
    )
    parser.add_argument(
        "--artifacts-root",
        default=None,
        help="repository root the register and the artifact are written under",
    )
    args = parser.parse_args(argv)

    root = Path(args.artifacts_root) if args.artifacts_root else REPO_ROOT
    run_dir = Path(args.run_dir) if args.run_dir else REPO_ROOT / "out" / "run"

    result = execute_run(run_dir)

    written = [
        register.write(result, root / register.REGISTER_PATH),
        cast.write(root / cast.CAST_PATH, run_dir / "cast.db"),
    ]
    (run_dir / "run.json").write_text(
        json.dumps(result.as_dict(), indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    _summarise(result, written, sys.stdout)
    return 0 if result.ok() else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
