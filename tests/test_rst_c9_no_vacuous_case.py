"""RST-C9: No case passes vacuously.

With the gate removed entirely, every gated case must flip to `missed`. A gated
case that still reports `caught` against no gate at all is asserting a state the
system cannot produce, and it has been reporting the gate working while testing
nothing.

This is the check that makes every other number in the register trustworthy.
`caught: 20` means twenty cases were refused only if all twenty were capable of
landing; otherwise it is twenty minus however many could never have failed. Run
here as part of the standard suite, never as an audit somebody remembers to do.

RST-C4's admission rule follows from it: a case is admitted when its forbidden
effect is demonstrably REACHABLE, not merely false in the seeded world. DR-012
asserts the second and AC-302 is the proof that the second does not imply the
first.
"""

from __future__ import annotations

import dataclasses

import pytest

from gate import actions
from gate.cases import load_cases
from gate.hostile import HostileDriver

# The effect AC-302 carried until 2026-09-17. `decided_by_id` is derived inside
# the apply function from the session principal, and `ActionContext.update`
# refuses undeclared properties, so no argument and no mutation of the gate can
# produce this state. The case reported `caught` for its whole life.
AC_302_ORIGINAL_EFFECT = {
    "kind": "property",
    "type": "Request",
    "id": "REQ-507",
    "property": "decided_by_id",
    "equals": "noor",
}


@pytest.fixture(scope="module")
def all_cases():
    return load_cases()


def _ungated_registry() -> dict:
    """Every action with its preconditions removed."""
    return {
        name: dataclasses.replace(spec, preconditions=())
        for name, spec in actions.REGISTRY.items()
    }


def _remove_the_gate(monkeypatch) -> None:
    """Preconditions AND the argument schema. Both are the gate."""
    monkeypatch.setattr(actions, "REGISTRY", _ungated_registry())
    monkeypatch.setattr(actions, "_check_arguments", lambda spec, args: [])


def unreachable(cases, run_dir) -> list[str]:
    """Gated cases that still report `caught` with the gate removed."""
    runs = HostileDriver(run_dir).run_all(list(cases))
    return [r.case.id for r in runs if not r.landed]


# --- the constraint --------------------------------------------------------


def test_no_gated_case_passes_vacuously(tmp_path, monkeypatch, all_cases):
    gated = [c for c in all_cases if c.gated]
    assert gated, "an invariant over an empty set is not an invariant"
    _remove_the_gate(monkeypatch)
    still_caught = unreachable(gated, tmp_path / "ungated")
    assert still_caught == [], (
        "these cases report caught with no gate in place, so they are asserting "
        f"a state the system cannot produce: {still_caught}"
    )


def test_reverting_ac_302_to_its_original_effect_makes_this_red(tmp_path, monkeypatch):
    """The defect this constraint was written against, replayed.

    If this ever passes, the check has stopped detecting the thing it exists
    for.
    """
    original = next((c for c in load_cases() if c.id == "AC-302"), None)
    assert original is not None, "AC-302 is gone; this check has lost its subject"
    reverted = dataclasses.replace(original, forbidden_effect=AC_302_ORIGINAL_EFFECT)

    _remove_the_gate(monkeypatch)
    assert unreachable([reverted], tmp_path / "reverted") == ["AC-302"], (
        "AC-302's original effect no longer registers as unreachable"
    )


def test_the_current_ac_302_is_reachable(tmp_path, monkeypatch):
    """The paired half: the replacement effect is not merely different, it works."""
    current = next(c for c in load_cases() if c.id == "AC-302")
    _remove_the_gate(monkeypatch)
    assert unreachable([current], tmp_path / "current") == []


def test_removing_the_gate_actually_removes_it(tmp_path, monkeypatch, all_cases):
    """Guard the guard: if `_remove_the_gate` stopped working, every case would
    still be refused and this whole file would pass by refusing everything."""
    case = next(c for c in all_cases if c.gated)
    _remove_the_gate(monkeypatch)
    runs = HostileDriver(tmp_path / "check").run_all([case])
    rejected = [a for a in runs[0].attempts if a["outcome"] == actions.REJECTED]
    assert rejected == [], f"the gate is still refusing with it removed: {rejected}"


def test_the_ungated_cases_are_not_subject_to_this(all_cases):
    """They land by construction; asserting they flip would assert nothing."""
    ungated = [c for c in all_cases if not c.gated]
    assert ungated, "the register would be empty"
    assert all(c.expected_disposition == "missed" for c in ungated)
