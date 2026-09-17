"""The action layer: the only module in this package permitted to write.

Every mutation in the system passes through ``invoke``. It runs the same four
phases regardless of who called it:

    1. ARGUMENTS   strict schema. Unknown, missing or wrongly typed arguments
                   are refused before anything is read.
    2. RESOLUTION  identifiers become rows, or the call is refused.
    3. PRECONDITIONS  every rule the action declares is evaluated -- all of
                   them, so the rejection names every failure, not the first.
    4. APPLY       and only now is a write context opened.

The principal is a parameter of ``invoke``, not of the action's argument
schema. An agent therefore has no argument through which to name a principal:
it acts as whoever the harness bound it to, and the schema refuses the rest.
Every attempt, applied or rejected, appends one row to the forensic log.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from . import ontology
from .errors import ActionError
from .preconditions import (
    AMOUNT_IN_RANGE,
    AWAITING_DECISION,
    Facts,
    IN_DRAFT,
    IS_REQUESTER,
    NOT_SELF_APPROVAL,
    NOT_TERMINAL,
    Precondition,
    PRINCIPAL_ACTIVE,
    REASON_PRESENT,
    TITLE_PRESENT,
    WITHDRAWABLE,
    WITHIN_AUTHORITY,
)
from .store import ActionContext, Store

APPLIED = "APPLIED"
REJECTED = "REJECTED"


@dataclass(frozen=True)
class Param:
    name: str
    datatype: str  # "text" | "int"


@dataclass(frozen=True)
class ActionSpec:
    name: str
    doc: str
    params: tuple[Param, ...]
    preconditions: tuple[Precondition, ...]
    apply: Callable[[ActionContext, Facts, "Store"], dict]
    takes_request: bool = True


@dataclass
class Result:
    action: str
    principal_id: str
    outcome: str
    rejection_codes: tuple[str, ...] = ()
    message: str = ""
    effect: dict[str, Any] = field(default_factory=dict)
    seq: int = 0

    @property
    def applied(self) -> bool:
        return self.outcome == APPLIED

    def as_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "principal_id": self.principal_id,
            "outcome": self.outcome,
            "rejection_codes": list(self.rejection_codes),
            "message": self.message,
            "effect": dict(self.effect),
            "seq": self.seq,
        }


# ---------------------------------------------------------------------------
# apply functions -- each opens exactly one write context
# ---------------------------------------------------------------------------


def _next_request_id(store: Store) -> str:
    rows = store.query("SELECT request_id FROM requests")
    highest = 0
    for row in rows:
        suffix = str(row["request_id"]).rsplit("-", 1)[-1]
        if suffix.isdigit():
            highest = max(highest, int(suffix))
    return f"REQ-{highest + 1:03d}"


def _apply_create(ctx: ActionContext, facts: Facts, store: Store) -> dict:
    request_id = _next_request_id(store)
    ctx.insert(
        "Request",
        {
            "request_id": request_id,
            "title": facts.args["title"],
            "amount_cents": facts.args["amount_cents"],
            "state": ontology.DRAFT,
            "justification": facts.args["justification"],
            "decision_note": None,
            "risk_summary": None,
            "requester_id": facts.principal["person_id"],
            "decided_by_id": None,
        },
    )
    return {"created": request_id, "state": ontology.DRAFT}


def _apply_submit(ctx: ActionContext, facts: Facts, store: Store) -> dict:
    ctx.update("Request", facts.request["request_id"], {"state": ontology.SUBMITTED})
    return {"request_id": facts.request["request_id"], "state": ontology.SUBMITTED}


def _apply_amend(ctx: ActionContext, facts: Facts, store: Store) -> dict:
    ctx.update(
        "Request",
        facts.request["request_id"],
        {"amount_cents": facts.args["amount_cents"]},
    )
    return {
        "request_id": facts.request["request_id"],
        "amount_cents": facts.args["amount_cents"],
    }


def _apply_approve(ctx: ActionContext, facts: Facts, store: Store) -> dict:
    ctx.update(
        "Request",
        facts.request["request_id"],
        {
            "state": ontology.APPROVED,
            "decided_by_id": facts.principal["person_id"],
            "decision_note": "approved",
        },
    )
    return {"request_id": facts.request["request_id"], "state": ontology.APPROVED}


def _apply_reject(ctx: ActionContext, facts: Facts, store: Store) -> dict:
    ctx.update(
        "Request",
        facts.request["request_id"],
        {
            "state": ontology.REJECTED,
            "decided_by_id": facts.principal["person_id"],
            "decision_note": facts.args["reason"],
        },
    )
    return {"request_id": facts.request["request_id"], "state": ontology.REJECTED}


def _apply_withdraw(ctx: ActionContext, facts: Facts, store: Store) -> dict:
    ctx.update("Request", facts.request["request_id"], {"state": ontology.WITHDRAWN})
    return {"request_id": facts.request["request_id"], "state": ontology.WITHDRAWN}


# ---------------------------------------------------------------------------
# the registry
# ---------------------------------------------------------------------------

REGISTRY: dict[str, ActionSpec] = {}


def _register(spec: ActionSpec) -> ActionSpec:
    REGISTRY[spec.name] = spec
    return spec


_register(
    ActionSpec(
        name="create_request",
        doc="Raise a new request in DRAFT, owned by the acting principal.",
        params=(
            Param("title", "text"),
            Param("amount_cents", "int"),
            Param("justification", "text"),
        ),
        preconditions=(PRINCIPAL_ACTIVE, TITLE_PRESENT, AMOUNT_IN_RANGE),
        apply=_apply_create,
        takes_request=False,
    )
)

_register(
    ActionSpec(
        name="submit_request",
        doc="Move an owned DRAFT request to SUBMITTED.",
        params=(Param("request_id", "text"),),
        preconditions=(PRINCIPAL_ACTIVE, NOT_TERMINAL, IN_DRAFT, IS_REQUESTER),
        apply=_apply_submit,
    )
)

_register(
    ActionSpec(
        name="amend_amount",
        doc="Change the amount of an owned DRAFT request.",
        params=(Param("request_id", "text"), Param("amount_cents", "int")),
        preconditions=(
            PRINCIPAL_ACTIVE,
            NOT_TERMINAL,
            IN_DRAFT,
            IS_REQUESTER,
            AMOUNT_IN_RANGE,
        ),
        apply=_apply_amend,
    )
)

_register(
    ActionSpec(
        name="approve_request",
        doc="Approve a SUBMITTED request raised by someone else, within authority.",
        params=(Param("request_id", "text"),),
        preconditions=(
            PRINCIPAL_ACTIVE,
            NOT_TERMINAL,
            AWAITING_DECISION,
            NOT_SELF_APPROVAL,
            WITHIN_AUTHORITY,
        ),
        apply=_apply_approve,
    )
)

_register(
    ActionSpec(
        name="reject_request",
        doc="Reject a SUBMITTED request raised by someone else.",
        params=(Param("request_id", "text"), Param("reason", "text")),
        preconditions=(
            PRINCIPAL_ACTIVE,
            NOT_TERMINAL,
            AWAITING_DECISION,
            NOT_SELF_APPROVAL,
            REASON_PRESENT,
        ),
        apply=_apply_reject,
    )
)

_register(
    ActionSpec(
        name="withdraw_request",
        doc="Withdraw an owned request that has not yet been decided.",
        params=(Param("request_id", "text"),),
        preconditions=(PRINCIPAL_ACTIVE, NOT_TERMINAL, WITHDRAWABLE, IS_REQUESTER),
        apply=_apply_withdraw,
    )
)


def action_names() -> tuple[str, ...]:
    return tuple(sorted(REGISTRY))


# ---------------------------------------------------------------------------
# the boundary
# ---------------------------------------------------------------------------


def _check_arguments(spec: ActionSpec, args: Mapping[str, Any]) -> list[str]:
    codes: list[str] = []
    declared = {p.name: p for p in spec.params}
    if set(args) - set(declared):
        codes.append("UNKNOWN_ARGUMENT")
    if set(declared) - set(args):
        codes.append("MISSING_ARGUMENT")
    for name, param in declared.items():
        if name not in args:
            continue
        value = args[name]
        if param.datatype == "int":
            # bool is a subclass of int; a boolean is not an amount.
            if not isinstance(value, int) or isinstance(value, bool):
                codes.append("ARGUMENT_TYPE")
        elif param.datatype == "text":
            if not isinstance(value, str):
                codes.append("ARGUMENT_TYPE")
    return sorted(set(codes))


def _describe(spec: ActionSpec, codes: Sequence[str]) -> str:
    by_code = {p.code: p.description for p in spec.preconditions}
    by_code.update(
        {
            "UNKNOWN_ARGUMENT": "The call supplied an argument the action does not declare.",
            "MISSING_ARGUMENT": "The call omitted a declared argument.",
            "ARGUMENT_TYPE": "An argument was of the wrong type.",
            "REQUEST_NOT_FOUND": "No request carries that identifier.",
            "PRINCIPAL_NOT_FOUND": "No principal carries that identifier.",
        }
    )
    return " ".join(by_code.get(code, code) for code in codes)


def invoke(
    store: Store,
    principal_id: str,
    action_name: str,
    args: Mapping[str, Any] | None = None,
    *,
    case_id: str | None = None,
    via: str = "direct",
) -> Result:
    """Attempt an action. The only write path in the system."""
    args = dict(args or {})
    spec = REGISTRY.get(action_name)
    if spec is None:
        raise ActionError(f"unknown action {action_name!r}; known: {action_names()}")

    def refuse(codes: Sequence[str]) -> Result:
        codes = tuple(codes)
        seq = store.record_attempt(
            case_id=case_id,
            principal_id=principal_id,
            action=action_name,
            args=args,
            via=via,
            outcome=REJECTED,
            rejection_codes=codes,
            message=_describe(spec, codes),
        )
        return Result(
            action=action_name,
            principal_id=principal_id,
            outcome=REJECTED,
            rejection_codes=codes,
            message=_describe(spec, codes),
            seq=seq,
        )

    # 1. arguments
    argument_codes = _check_arguments(spec, args)
    if argument_codes:
        return refuse(argument_codes)

    # 2. resolution
    principal = store.get("Person", principal_id)
    if principal is None:
        return refuse(["PRINCIPAL_NOT_FOUND"])
    request = None
    if spec.takes_request:
        request = store.get("Request", args["request_id"])
        if request is None:
            return refuse(["REQUEST_NOT_FOUND"])

    facts = Facts(principal=principal, args=args, request=request)

    # 3. preconditions -- all of them
    failures = tuple(p.code for p in spec.preconditions if not p.holds(facts))
    if failures:
        return refuse(failures)

    # 4. apply
    with store.action_context(action_name, principal_id) as ctx:
        effect = spec.apply(ctx, facts, store)
    seq = store.record_attempt(
        case_id=case_id,
        principal_id=principal_id,
        action=action_name,
        args=args,
        via=via,
        outcome=APPLIED,
        rejection_codes=(),
        message="",
    )
    return Result(
        action=action_name,
        principal_id=principal_id,
        outcome=APPLIED,
        effect=effect,
        seq=seq,
    )
