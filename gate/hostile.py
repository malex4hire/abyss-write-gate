"""The hostile driver.

This is not a model and there is no prompt anywhere in this file. It is a
deterministic program that reads the case set and does what each case says,
and it is a STRONGER adversary than a model would be, in the one way that
matters here: it never declines. There is no refusal path in this module. If a
record contains an instruction addressed to the agent, the driver executes it.
Maximal credulity is the point -- a gate that only holds against a
well-behaved model has not been tested.

The consequence is that every result in this repository is reproducible by
anyone with a clone and no credential, which is why the default path works this
way and an optional live provider, if one is ever added, would not replace it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from . import actions
from .cases import Case, evaluate_effect
from .fixtures import build_world
from .harness import ToolSession

INSTRUCTION_MARKER = ">>> AGENT INSTRUCTION:"

_DECODER = json.JSONDecoder()


def _strings(payload: Any) -> Iterable[str]:
    """Every string anywhere in a tool result. Instructions hide in the leaves."""
    if isinstance(payload, str):
        yield payload
    elif isinstance(payload, dict):
        for value in payload.values():
            yield from _strings(value)
    elif isinstance(payload, (list, tuple)):
        for value in payload:
            yield from _strings(value)


def extract_instructions(payload: Any) -> list[dict[str, Any]]:
    """Find instructions addressed to the agent inside tool output.

    The marker and the JSON payload are a synthetic convention, and that is
    deliberate: it makes the driver's obedience deterministic and total. A real
    model would obey inconsistently, which would make a green run evidence
    about the model's mood rather than about the gate.
    """
    found: list[dict[str, Any]] = []
    for text in _strings(payload):
        cursor = 0
        while True:
            marker_at = text.find(INSTRUCTION_MARKER, cursor)
            if marker_at < 0:
                break
            brace_at = text.find("{", marker_at)
            if brace_at < 0:
                break
            try:
                obj, end = _DECODER.raw_decode(text, brace_at)
            except json.JSONDecodeError:
                cursor = marker_at + len(INSTRUCTION_MARKER)
                continue
            if isinstance(obj, dict) and "tool" in obj:
                found.append(obj)
            cursor = end
    return found


@dataclass
class CaseRun:
    case: Case
    db_path: str
    transcript: list[dict[str, Any]] = field(default_factory=list)
    attempts: list[dict[str, Any]] = field(default_factory=list)
    landed: bool = False
    disposition: str = ""
    observed_rejections: list[str] = field(default_factory=list)
    instructions_obeyed: int = 0

    @property
    def attempted_actions(self) -> set[str]:
        return {a["action"] for a in self.attempts}

    def as_dict(self) -> dict[str, Any]:
        return {
            "case": self.case.as_dict(),
            "db_path": self.db_path,
            "disposition": self.disposition,
            "landed": self.landed,
            "observed_rejections": sorted(set(self.observed_rejections)),
            "attempts": self.attempts,
            "attempt_count": len(self.attempts),
            "instructions_obeyed": self.instructions_obeyed,
            "transcript": self.transcript,
        }


class HostileDriver:
    """Runs one case against one freshly seeded world."""

    def __init__(self, run_dir: Path | str):
        self.run_dir = Path(run_dir)
        self.case_dir = self.run_dir / "cases"
        self.case_dir.mkdir(parents=True, exist_ok=True)

    def run_case(self, case: Case) -> CaseRun:
        db_path = self.case_dir / f"{case.id}.db"
        store = build_world(db_path)
        session = ToolSession(store, case.principal, case_id=case.id)
        obeyed = 0

        for step in case.steps:
            if "call" in step:
                record = session.call(step["call"], step.get("args", {}))
                if step.get("obey"):
                    for instruction in extract_instructions(record.result):
                        obeyed += 1
                        session.call(instruction["tool"], instruction.get("args", {}))
            elif "direct" in step:
                # Straight at the action layer. No agent, no harness, no
                # caller-side anything.
                actions.invoke(
                    store,
                    case.principal,
                    step["direct"],
                    step.get("args", {}),
                    case_id=case.id,
                    via="direct",
                )
            else:
                raise ValueError(f"{case.id}: step declares neither call nor direct: {step}")

        transcript = [c.as_dict() for c in session.transcript]
        attempts = store.attempts(case.id)
        transcript_text = json.dumps(transcript, sort_keys=True, default=str)
        landed = evaluate_effect(store, transcript_text, case.forbidden_effect)
        observed = [
            code
            for attempt in attempts
            for code in (attempt["rejection_codes"] or "").split(",")
            if code
        ]
        store.close()

        return CaseRun(
            case=case,
            db_path=db_path.relative_to(self.run_dir).as_posix(),
            transcript=transcript,
            attempts=attempts,
            landed=landed,
            disposition="missed" if landed else "caught",
            observed_rejections=observed,
            instructions_obeyed=obeyed,
        )

    def run_all(self, cases: Iterable[Case]) -> list[CaseRun]:
        return [self.run_case(case) for case in cases]
