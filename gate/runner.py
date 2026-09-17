"""Orchestration: run the adversarial set and reduce it to a result.

Every case gets its OWN freshly seeded database. Cases do not share state and
cannot see each other, so a disposition is a property of the case rather than
of where it happened to sit in the ordering. The databases are retained in the
run directory afterwards, because a rejected attempt is a forensic record and
the whole point of keeping it is that someone can open it later and look.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from .cases import CAUGHT, MISSED, Case, load_cases
from .hostile import CaseRun, HostileDriver

MISMATCH = "MISMATCH"


@dataclass
class RunResult:
    run_dir: Path
    runs: list[CaseRun]

    # ---- reductions -------------------------------------------------------

    @property
    def cases(self) -> list[Case]:
        return [r.case for r in self.runs]

    @property
    def caught(self) -> list[CaseRun]:
        return [r for r in self.runs if r.disposition == CAUGHT]

    @property
    def missed(self) -> list[CaseRun]:
        return [r for r in self.runs if r.disposition == MISSED]

    @property
    def gated(self) -> list[CaseRun]:
        return [r for r in self.runs if r.case.gated]

    @property
    def ungated(self) -> list[CaseRun]:
        return [r for r in self.runs if not r.case.gated]

    @property
    def mismatches(self) -> list[CaseRun]:
        """Cases whose observed disposition differs from the declared one."""
        return [
            r for r in self.runs if r.disposition != r.case.expected_disposition
        ]

    @property
    def unmet_expectations(self) -> list[tuple[str, list[str], list[str]]]:
        """Caught cases where the gate refused for reasons other than declared."""
        out = []
        for run in self.runs:
            expected = set(run.case.expected_rejections)
            observed = set(run.observed_rejections)
            if expected and not expected <= observed:
                out.append((run.case.id, sorted(expected), sorted(observed)))
        return out

    @property
    def total_attempts(self) -> int:
        return sum(len(r.attempts) for r in self.runs)

    def by_class(self) -> dict[str, list[CaseRun]]:
        grouped: dict[str, list[CaseRun]] = {}
        for run in self.runs:
            grouped.setdefault(run.case.cls, []).append(run)
        return grouped

    def by_reason_class(self) -> dict[str, list[CaseRun]]:
        grouped: dict[str, list[CaseRun]] = {}
        for run in self.missed:
            grouped.setdefault(run.case.miss_reason_class or "UNDECLARED", []).append(run)
        return grouped

    def counts(self) -> dict[str, int]:
        """Every number the register publishes, computed here exactly once."""
        return {
            "cases": len(self.runs),
            "classes": len(self.by_class()),
            "caught": len(self.caught),
            "missed": len(self.missed),
            "gated": len(self.gated),
            "ungated": len(self.ungated),
            "attempts": self.total_attempts,
            "reason_classes": len(self.by_reason_class()),
            "forbidden_mutations_landed": sum(1 for r in self.gated if r.landed),
        }

    def ok(self) -> bool:
        return not self.mismatches and not self.unmet_expectations

    def as_dict(self) -> dict[str, Any]:
        return {
            "counts": self.counts(),
            "runs": [r.as_dict() for r in self.runs],
        }


def execute_run(run_dir: Path | str, cases: Sequence[Case] | None = None) -> RunResult:
    cases = list(cases) if cases is not None else load_cases()
    driver = HostileDriver(run_dir)
    runs = driver.run_all(cases)
    return RunResult(run_dir=Path(run_dir), runs=runs)
