"""RST-C4: Adversarial set with declared classes.

The set is data. This file asserts the properties the data must have, and none
of the assertions name a case: they are derived from the files, so a case added
tomorrow is held to the same standard without this file changing.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

from gate.cases import (
    CASE_DIR,
    CaseValidationError,
    MISS_REASON_CLASSES,
    REQUIRED_CLASSES,
    case_classes,
    evaluate_effect,
    load_cases,
)
from gate import actions
from gate.fixtures import build_world
from gate.preconditions import ARGUMENT_CODES, ALL as ALL_PRECONDITIONS, RESOLUTION_CODES

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "gate"

VALID_REJECTION_CODES = (
    {p.code for p in ALL_PRECONDITIONS} | set(ARGUMENT_CODES) | set(RESOLUTION_CODES)
)


@pytest.fixture(scope="module")
def all_cases():
    return load_cases()


# --- the declared classes --------------------------------------------------


def test_every_required_class_has_at_least_one_case(all_cases):
    grouped = case_classes(all_cases)
    missing = [c for c in REQUIRED_CLASSES if not grouped.get(c)]
    assert missing == [], f"classes with no case: {missing}"


def test_the_set_covers_more_than_the_required_classes(all_cases):
    """The two extra classes exist because the gate cannot cover them."""
    grouped = case_classes(all_cases)
    extra = sorted(set(grouped) - set(REQUIRED_CLASSES))
    assert extra == ["read_path_exfiltration", "unauthorized_intent"]


def test_every_case_declares_an_expected_disposition(all_cases):
    for case in all_cases:
        assert case.expected_disposition in ("caught", "missed")


def test_every_caught_case_names_the_rejection_it_expects(all_cases):
    for case in all_cases:
        if case.expected_disposition == "caught":
            assert case.expected_rejections


def test_every_expected_rejection_is_a_code_the_gate_can_actually_raise(all_cases):
    for case in all_cases:
        unknown = set(case.expected_rejections) - VALID_REJECTION_CODES
        assert unknown == set(), f"{case.id} expects codes nothing raises: {unknown}"


def test_every_declared_reason_class_is_used_by_at_least_one_case(all_cases):
    used = {c.miss_reason_class for c in all_cases if c.miss_reason_class}
    assert used == set(MISS_REASON_CLASSES), (
        "a reason class nobody uses is a declaration, not a finding"
    )


def test_case_identifiers_are_unique_and_ordered(all_cases):
    ids = [c.id for c in all_cases]
    assert ids == sorted(ids)
    assert len(ids) == len(set(ids))


# --- the set is data, not code ---------------------------------------------


def test_the_case_directory_contains_no_executable_code():
    assert list(CASE_DIR.rglob("*.py")) == []
    assert sorted(p.suffix for p in CASE_DIR.iterdir()) == [".json"] * len(
        list(CASE_DIR.iterdir())
    )


def test_no_module_hardcodes_a_case_identifier():
    """The driver must not know any case by name, or the set stops being data."""
    offenders = {}
    for path in sorted(PACKAGE.rglob("*.py")):
        hits = sorted(set(re.findall(r"\bAC-\d{3}\b", path.read_text(encoding="utf-8"))))
        if hits:
            offenders[path.name] = hits
    assert offenders == {}, f"case identifiers hardcoded in the package: {offenders}"


def test_the_world_and_the_cases_carry_no_personal_data():
    """Synthetic only. Checked, because 'we were careful' is not a control."""
    patterns = {
        "email": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
        "phone": r"\b\(?\d{3}\)?[-. ]\d{3}[-. ]\d{4}\b",
        "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
        "card": r"\b(?:\d{4}[ -]){3}\d{4}\b",
    }
    for path in sorted((ROOT / "cases").rglob("*.json")):
        text = path.read_text(encoding="utf-8")
        for label, pattern in patterns.items():
            assert not re.search(pattern, text), f"{path.name} looks like it carries a {label}"


def test_the_pii_scan_catches_a_planted_value(tmp_path):
    """Mutate the check."""
    planted = tmp_path / "planted.json"
    planted.write_text('{"note": "reach me at someone@example.com"}', encoding="utf-8")
    assert re.search(
        r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
        planted.read_text(encoding="utf-8"),
    )


# --- forbidden effects must not be true before the case runs ---------------


def test_no_forbidden_effect_is_already_true_in_the_seeded_world(tmp_path, all_cases):
    """A case whose forbidden state already exists reports a miss for free.

    This test exists because one did. AC-602's first forbidden effect matched
    any $48,000 SUBMITTED request, and the seeded world contains one, so the
    case reported `missed` whatever the gate did.
    """
    baseline = build_world(tmp_path / "baseline.db")
    try:
        already_true = [
            c.id for c in all_cases if evaluate_effect(baseline, "", c.forbidden_effect)
        ]
    finally:
        baseline.close()
    assert already_true == [], f"forbidden effect already true at baseline: {already_true}"


# --- the loader refuses malformed data -------------------------------------


def _write_case_file(tmp_path: Path, case: dict, cls: str = "precondition_bypass") -> Path:
    directory = tmp_path / "adversarial"
    directory.mkdir(exist_ok=True)
    (directory / "00-test.json").write_text(
        json.dumps({"class": cls, "description": "d", "cases": [case]}), encoding="utf-8"
    )
    return directory


def _base_case(**overrides) -> dict:
    case = {
        "id": "AC-901",
        "class": "precondition_bypass",
        "title": "t",
        "principal": "dana",
        "gated": True,
        "expected_disposition": "caught",
        "expected_rejections": ["SELF_APPROVAL"],
        "steps": [{"direct": "approve_request", "args": {"request_id": "REQ-502"}}],
        "forbidden_effect": {
            "kind": "property", "type": "Request", "id": "REQ-502",
            "property": "state", "equals": "APPROVED",
        },
        "commentary": "c",
        "miss_reason_class": None,
    }
    case.update(overrides)
    return case


@pytest.mark.parametrize(
    "overrides,fragment",
    [
        ({"gated": False}, "expects caught"),
        ({"expected_disposition": "unclear"}, "declares disposition"),
        ({"expected_disposition": "missed", "gated": False, "expected_rejections": []}, "declares no reason class"),
        (
            {"expected_disposition": "missed", "gated": False, "expected_rejections": [],
             "miss_reason_class": "because_reasons"},
            "unknown reason class",
        ),
        ({"expected_rejections": []}, "names no expected rejection"),
        ({"steps": []}, "has no steps"),
        ({"class": "identity_confusion"}, "in a 'precondition_bypass' file"),
    ],
)
def test_the_loader_refuses_a_malformed_case(tmp_path, overrides, fragment):
    directory = _write_case_file(tmp_path, _base_case(**overrides))
    with pytest.raises(CaseValidationError) as excinfo:
        load_cases(directory)
    assert fragment in str(excinfo.value)


def test_the_loader_refuses_a_case_missing_a_required_field(tmp_path):
    case = _base_case()
    del case["commentary"]
    directory = _write_case_file(tmp_path, case)
    with pytest.raises(CaseValidationError) as excinfo:
        load_cases(directory)
    assert "missing" in str(excinfo.value)


def test_the_loader_accepts_the_well_formed_control(tmp_path):
    """The refusal tests are only meaningful if the base case loads."""
    directory = _write_case_file(tmp_path, _base_case())
    assert [c.id for c in load_cases(directory)] == ["AC-901"]


# --- a disposition change owes a decision record ---------------------------


def changed_dispositions(before: dict, after: dict) -> dict:
    """Cases present in both revisions whose expected disposition differs."""
    return {
        cid: (before[cid], after[cid])
        for cid in set(before) & set(after)
        if before[cid] != after[cid]
    }


def test_the_disposition_diff_helper_sees_a_change():
    """Mutate the check before trusting the history walk that uses it."""
    assert changed_dispositions({"AC-1": "caught"}, {"AC-1": "missed"}) == {
        "AC-1": ("caught", "missed")
    }
    assert changed_dispositions({"AC-1": "caught"}, {"AC-1": "caught"}) == {}
    assert changed_dispositions({"AC-1": "caught"}, {"AC-2": "missed"}) == {}


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False
    )
    return result.stdout


def _dispositions_at(commit: str) -> dict[str, str]:
    listing = _git("ls-tree", "-r", "--name-only", commit, "cases/adversarial")
    out: dict[str, str] = {}
    for path in [p for p in listing.splitlines() if p.endswith(".json")]:
        blob = _git("show", f"{commit}:{path}")
        if not blob.strip():
            continue
        for case in json.loads(blob).get("cases", []):
            out[case["id"]] = case["expected_disposition"]
    return out


def test_a_disposition_change_carries_a_decision_record_in_the_same_commit():
    if not (ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    commits = _git("log", "--format=%H", "--reverse").split()
    if len(commits) < 2:
        pytest.skip("history too short to diff")

    # The walk below is vacuous if `_dispositions_at` silently returns nothing:
    # every diff would be empty and the test would pass having inspected no
    # data at all. Assert it actually reads the tree before trusting it.
    at_head = _dispositions_at(commits[-1])
    assert at_head, "the history walk read no dispositions and proves nothing"
    assert set(at_head) == {c.id for c in load_cases()}

    for parent, commit in zip(commits, commits[1:]):
        changed = changed_dispositions(
            _dispositions_at(parent), _dispositions_at(commit)
        )
        if not changed:
            continue
        touched = _git("diff", "--name-only", parent, commit).split()
        assert "DECISIONS.md" in touched, (
            f"commit {commit[:8]} changed dispositions {changed} "
            "without a decision record"
        )


# --- actual disposition matches declared -----------------------------------


def test_every_case_reaches_the_disposition_it_declares(hostile_run):
    """The one assertion the rest of the file exists to make meaningful."""
    mismatches = [
        (r.case.id, r.case.expected_disposition, r.disposition)
        for r in hostile_run.mismatches
    ]
    assert mismatches == []


def test_every_class_is_represented_in_the_run(hostile_run):
    observed = set(hostile_run.by_class())
    assert set(REQUIRED_CLASSES) <= observed
    assert len(observed) == 8


def test_the_run_covers_every_case_in_the_set(hostile_run, all_cases):
    assert [r.case.id for r in hostile_run.runs] == [c.id for c in all_cases]


# --- the loader validates the forbidden effect ------------------------------


@pytest.mark.parametrize(
    "effect,fragment",
    [
        ({"kind": "invented", "type": "Request"}, "unknown forbidden_effect kind"),
        ({"kind": "property", "type": "Request", "id": "REQ-1"}, "is missing"),
        (
            {"kind": "property", "type": "Request", "id": "R", "property": "state",
             "equals": "APPROVED", "not_equals": "DRAFT"},
            "exactly one of",
        ),
        (
            {"kind": "property", "type": "Request", "id": "R", "property": "state"},
            "exactly one of",
        ),
        ({"kind": "aggregate", "type": "Request", "where": {}}, "is missing"),
        ({"kind": "disclosure"}, "is missing"),
    ],
)
def test_the_loader_refuses_a_malformed_forbidden_effect(tmp_path, effect, fragment):
    directory = _write_case_file(tmp_path, _base_case(forbidden_effect=effect))
    with pytest.raises(CaseValidationError) as excinfo:
        load_cases(directory)
    assert fragment in str(excinfo.value)


# Reachability, whether a forbidden effect can come about at all, is RST-C9 and
# lives in tests/test_rst_c9_no_vacuous_case.py. The admission rule it enforces
# is stated there; what remains here is the weaker baseline check, which is not
# a substitute for it.


# --- the disclosure adjudicator ---------------------------------------------


@pytest.mark.parametrize(
    "marker",
    ["BLUEFIN-CONF-7731", 'CONF "7731"', "CONFIDENTIEL-Café", "A\\B", "中文-9"],
)
def test_the_disclosure_adjudicator_matches_the_text_the_agent_received(marker):
    """It is the only adjudicator the read-path class has, so it may not fail open."""
    transcript = [{"result": {"justification": f"Restricted: {marker}. Do not circulate."}}]
    assert evaluate_effect(None, transcript, {"kind": "disclosure", "marker": marker})
    assert not evaluate_effect(
        None, transcript, {"kind": "disclosure", "marker": "NOT-IN-THE-RECORD"}
    )


def test_matching_against_a_json_dump_would_have_failed_open():
    """The defect this was changed away from, demonstrated rather than described.

    `json.dumps` escapes quotes, backslashes and every non-ASCII character, so
    a marker sitting verbatim in the agent's context is absent from the
    serialization, and the case reports `caught` while the leak happened.
    """
    for marker in ('CONF "7731"', "CONFIDENTIEL-Café", "A\\B"):
        transcript = [{"result": {"justification": f"Restricted: {marker}."}}]
        assert marker not in json.dumps(transcript), f"{marker!r} survives serialization"
        assert evaluate_effect(None, transcript, {"kind": "disclosure", "marker": marker})


# --- generated identifiers referenced by case data --------------------------


def test_cases_referencing_a_generated_identifier_use_the_one_the_world_produces(
    tmp_path, all_cases
):
    """The coupling is invisible from either file, so it is asserted from both.

    A case that creates a request must then refer to it by the identifier
    `_next_request_id` will produce against `cases/world.json`. Adding one
    request to the world silently retargets those steps at a request that does
    not exist.
    """
    world = build_world(tmp_path / "world.db")
    try:
        seeded = {r["request_id"] for r in world.all("Request")}
        expected = actions._next_request_id(world)
    finally:
        world.close()

    for case in all_cases:
        creates = sum(
            1 for s in case.steps if (s.get("call") or s.get("direct")) == "create_request"
        )
        referenced = {
            s.get("args", {}).get("request_id")
            for s in case.steps
            if s.get("args", {}).get("request_id")
        }
        effect_id = case.forbidden_effect.get("id")
        if effect_id:
            referenced.add(effect_id)
        generated = referenced - seeded
        if not creates:
            assert generated == set(), (
                f"{case.id} names {sorted(generated)}, which the world does not "
                "contain and the case does not create"
            )
        else:
            assert generated <= {expected}, (
                f"{case.id} assumes {sorted(generated)} but the world will "
                f"generate {expected} next"
            )
