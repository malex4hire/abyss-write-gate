"""RST-C2 -- Preconditions attach to the action, not the caller.

Every case here invokes the action layer DIRECTLY. There is no agent in this
file. If a rule only holds when the agent harness is in the call stack, nothing
in this file passes.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from gate import actions, ontology, preconditions
from gate.preconditions import Facts, Precondition

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "gate"

# (action, principal, args, codes that MUST appear in the rejection)
VIOLATIONS = [
    # create_request
    ("create_request", "sam", {"title": "t", "amount_cents": 100, "justification": "j"}, {"PRINCIPAL_INACTIVE"}),
    ("create_request", "dana", {"title": "   ", "amount_cents": 100, "justification": "j"}, {"TITLE_EMPTY"}),
    ("create_request", "dana", {"title": "t", "amount_cents": 0, "justification": "j"}, {"AMOUNT_OUT_OF_RANGE"}),
    ("create_request", "dana", {"title": "t", "amount_cents": 100_000_001, "justification": "j"}, {"AMOUNT_OUT_OF_RANGE"}),
    # submit_request
    ("submit_request", "sam", {"request_id": "REQ-503"}, {"PRINCIPAL_INACTIVE"}),
    ("submit_request", "eli", {"request_id": "REQ-505"}, {"TERMINAL_STATE", "NOT_IN_DRAFT"}),
    ("submit_request", "eli", {"request_id": "REQ-501"}, {"NOT_IN_DRAFT"}),
    ("submit_request", "dana", {"request_id": "REQ-503"}, {"NOT_REQUESTER"}),
    # amend_amount
    ("amend_amount", "sam", {"request_id": "REQ-503", "amount_cents": 500}, {"PRINCIPAL_INACTIVE"}),
    ("amend_amount", "eli", {"request_id": "REQ-505", "amount_cents": 500}, {"TERMINAL_STATE"}),
    ("amend_amount", "eli", {"request_id": "REQ-501", "amount_cents": 500}, {"NOT_IN_DRAFT"}),
    ("amend_amount", "dana", {"request_id": "REQ-503", "amount_cents": 500}, {"NOT_REQUESTER"}),
    ("amend_amount", "eli", {"request_id": "REQ-503", "amount_cents": 0}, {"AMOUNT_OUT_OF_RANGE"}),
    # approve_request
    ("approve_request", "sam", {"request_id": "REQ-501"}, {"PRINCIPAL_INACTIVE"}),
    ("approve_request", "dana", {"request_id": "REQ-504"}, {"TERMINAL_STATE", "NOT_AWAITING_DECISION"}),
    ("approve_request", "dana", {"request_id": "REQ-503"}, {"NOT_AWAITING_DECISION"}),
    ("approve_request", "dana", {"request_id": "REQ-502"}, {"SELF_APPROVAL"}),
    ("approve_request", "dana", {"request_id": "REQ-501"}, {"ABOVE_AUTHORITY"}),
    # reject_request
    ("reject_request", "sam", {"request_id": "REQ-501", "reason": "no"}, {"PRINCIPAL_INACTIVE"}),
    ("reject_request", "dana", {"request_id": "REQ-504", "reason": "no"}, {"TERMINAL_STATE", "NOT_AWAITING_DECISION"}),
    ("reject_request", "dana", {"request_id": "REQ-503", "reason": "no"}, {"NOT_AWAITING_DECISION"}),
    ("reject_request", "dana", {"request_id": "REQ-502", "reason": "no"}, {"SELF_APPROVAL"}),
    ("reject_request", "dana", {"request_id": "REQ-501", "reason": "  "}, {"REASON_EMPTY"}),
    # withdraw_request
    ("withdraw_request", "sam", {"request_id": "REQ-501"}, {"PRINCIPAL_INACTIVE"}),
    ("withdraw_request", "eli", {"request_id": "REQ-505"}, {"TERMINAL_STATE", "NOT_WITHDRAWABLE"}),
    ("withdraw_request", "dana", {"request_id": "REQ-501"}, {"NOT_REQUESTER"}),
]

ARGUMENT_VIOLATIONS = [
    ("approve_request", "dana", {"request_id": "REQ-507", "principal_id": "noor"}, {"UNKNOWN_ARGUMENT"}),
    ("approve_request", "dana", {}, {"MISSING_ARGUMENT"}),
    ("amend_amount", "eli", {"request_id": "REQ-503", "amount_cents": "9000"}, {"ARGUMENT_TYPE"}),
    ("amend_amount", "eli", {"request_id": "REQ-503", "amount_cents": True}, {"ARGUMENT_TYPE"}),
    ("approve_request", "dana", {"request_id": 507}, {"ARGUMENT_TYPE"}),
    ("approve_request", "dana", {"request_id": "REQ-000"}, {"REQUEST_NOT_FOUND"}),
    ("approve_request", "nobody", {"request_id": "REQ-507"}, {"PRINCIPAL_NOT_FOUND"}),
]


def _snapshot(store):
    return {r["request_id"]: dict(r) for r in store.all("Request")}


@pytest.mark.parametrize("action,principal,args,expected", VIOLATIONS + ARGUMENT_VIOLATIONS)
def test_a_direct_invocation_with_violating_arguments_is_rejected(
    store, action, principal, args, expected
):
    before = _snapshot(store)
    result = actions.invoke(store, principal, action, args)
    assert not result.applied, f"{action} by {principal} landed and should not have"
    assert expected <= set(result.rejection_codes), (
        f"{action} by {principal}: expected {sorted(expected)}, "
        f"got {sorted(result.rejection_codes)}"
    )
    assert _snapshot(store) == before, "a rejected action changed persisted state"


def test_every_declared_precondition_is_exercised_by_a_violating_case(store):
    """Coverage is asserted, not hoped for.

    Adding a precondition to an action without a case that violates it fails
    here, which is what stops the rule set and the case table drifting apart.
    """
    observed: set[tuple[str, str]] = set()
    for action, principal, args, _ in VIOLATIONS:
        result = actions.invoke(store, principal, action, args)
        for code in result.rejection_codes:
            observed.add((action, code))
    declared = {
        (name, p.code)
        for name, spec in actions.REGISTRY.items()
        for p in spec.preconditions
    }
    assert declared - observed == set(), f"unexercised preconditions: {sorted(declared - observed)}"


def test_the_outcome_is_identical_whichever_caller_invokes_it(store):
    """Remove all caller-side validation and nothing changes.

    ``validating_caller`` checks the rule before calling; ``naive_caller``
    checks nothing at all and calls straight through. If any precondition lived
    in a caller, these two would disagree.
    """

    def validating_caller(st, principal, action, args):
        request = st.get("Request", args["request_id"])
        if request and request["requester_id"] == principal:
            return "caller refused"
        return actions.invoke(st, principal, action, args)

    def naive_caller(st, principal, action, args):
        return actions.invoke(st, principal, action, args)

    for caller in (naive_caller, validating_caller):
        before = _snapshot(store)
        outcome = caller(store, "dana", "approve_request", {"request_id": "REQ-502"})
        assert _snapshot(store) == before
        if outcome != "caller refused":
            assert "SELF_APPROVAL" in outcome.rejection_codes


def test_no_module_outside_the_rule_layer_mentions_a_rejection_code():
    """A rule re-implemented in a caller is a second rule that can drift."""
    codes = {p.code for p in preconditions.ALL}
    allowed = {"gate/preconditions.py", "gate/actions.py"}
    offenders = {}
    for path in sorted(PACKAGE.rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if rel in allowed:
            continue
        text = path.read_text(encoding="utf-8")
        # Whole-token match. `TERMINAL_STATES` in the ontology is not a
        # reference to the `TERMINAL_STATE` rejection code, and a substring
        # check that says it is has a false positive -- which is worse than no
        # check, because the next reader disables it.
        hits = sorted(
            code
            for code in codes
            if re.search(rf"(?<![A-Za-z0-9_]){code}(?![A-Za-z0-9_])", text)
        )
        if hits:
            offenders[rel] = hits
    assert offenders == {}, f"rejection codes referenced outside the rule layer: {offenders}"


# --- provenance: no rule may read model output -----------------------------


def _model_derived_reads(rules) -> dict[str, list[str]]:
    offenders: dict[str, list[str]] = {}
    for rule in rules:
        bad = [
            ref
            for ref in rule.reads
            if ontology.resolve_property(ref).provenance == ontology.MODEL_DERIVED
        ]
        if bad:
            offenders[rule.code] = bad
    return offenders


def test_no_precondition_reads_a_model_derived_property():
    assert _model_derived_reads(preconditions.ALL) == {}


def test_the_provenance_check_catches_a_planted_model_derived_read():
    """Mutate the check, not only the subject."""
    planted = Precondition(
        code="PLANTED",
        description="Reads a model's opinion.",
        reads=("Request.risk_summary",),
        holds=lambda f: True,
    )
    assert _model_derived_reads([planted]) == {"PLANTED": ["Request.risk_summary"]}


def test_the_ontology_actually_declares_a_model_derived_property():
    """A separation test over an empty set is vacuous. Assert the set is not empty."""
    derived = [p.name for p in ontology.REQUEST.model_derived]
    assert derived == ["risk_summary"]


def test_the_rule_layer_never_names_a_model_derived_property_in_source():
    """The declared reads could be honest while the predicate cheats.

    A rule could declare only measured reads and then reach for
    ``request["risk_summary"]`` inside its lambda. The declaration check would
    stay green. So check the source too: no model-derived property name appears
    anywhere in the rule layer.
    """
    source = (PACKAGE / "preconditions.py").read_text(encoding="utf-8")
    for obj in ontology.OBJECT_TYPES:
        for prop in obj.model_derived:
            assert prop.name not in source, (
                f"preconditions.py names the model-derived property {prop.name!r}"
            )


def test_the_source_provenance_check_catches_a_planted_reach(tmp_path):
    """Mutate the check: plant the reach and require the scan to see it."""
    planted = tmp_path / "rogue_rules.py"
    planted.write_text(
        "RULE = lambda f: f.request['risk_summary'] != 'high'\n", encoding="utf-8"
    )
    derived_names = [p.name for o in ontology.OBJECT_TYPES for p in o.model_derived]
    text = planted.read_text(encoding="utf-8")
    assert [n for n in derived_names if n in text] == ["risk_summary"]


def test_every_declared_read_resolves_against_the_ontology():
    for rule in preconditions.ALL:
        for ref in rule.reads:
            assert ontology.resolve_property(ref) is not None


def test_a_precondition_with_an_unresolvable_read_cannot_be_constructed():
    with pytest.raises(KeyError):
        Precondition(
            code="TYPO",
            description="Reads a property that does not exist.",
            reads=("Request.amount_dollars",),
            holds=lambda f: True,
        )


def test_preconditions_are_pure_over_facts():
    """A rule is a predicate over resolved facts and has no other input."""
    facts = Facts(
        principal={"person_id": "dana", "active": 1, "authority_limit_cents": 1000000},
        args={},
        request={"request_id": "REQ-X", "state": ontology.SUBMITTED,
                 "requester_id": "eli", "amount_cents": 500},
    )
    assert preconditions.NOT_SELF_APPROVAL.holds(facts) is True
    assert preconditions.WITHIN_AUTHORITY.holds(facts) is True
    facts_self = Facts(
        principal=facts.principal, args={},
        request={**facts.request, "requester_id": "dana"},
    )
    assert preconditions.NOT_SELF_APPROVAL.holds(facts_self) is False
