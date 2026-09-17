"""Preconditions, declared as data.

A precondition is a code, a sentence, the set of ontology properties it reads,
and a pure predicate over resolved facts. It is attached to an ACTION, never to
a caller, so it holds identically whether the caller is the agent harness, a
test, or a hostile driver invoking the action layer directly.

Two properties of this module are asserted by tests rather than intended:

  * ``reads`` entries must resolve against the ontology, and every property
    they resolve to must be MEASURED. No rule may depend on model output.
  * Preconditions are evaluated exhaustively, not short-circuited, so a
    rejection names every rule that failed rather than the first one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from . import ontology

MAX_AMOUNT_CENTS = 100_000_000  # $1,000,000. Nothing in this world is larger.


@dataclass(frozen=True)
class Facts:
    """Everything a precondition may look at."""

    principal: Mapping[str, Any]
    args: Mapping[str, Any]
    request: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class Precondition:
    code: str
    description: str
    reads: tuple[str, ...]
    holds: Callable[[Facts], bool]

    def __post_init__(self) -> None:
        for ref in self.reads:
            ontology.resolve_property(ref)  # raises on a typo


PRINCIPAL_ACTIVE = Precondition(
    code="PRINCIPAL_INACTIVE",
    description="The acting principal must be active.",
    reads=("Person.active",),
    holds=lambda f: bool(f.principal["active"]),
)

NOT_TERMINAL = Precondition(
    code="TERMINAL_STATE",
    description="A request in a terminal state does not transition again.",
    reads=("Request.state",),
    holds=lambda f: f.request["state"] not in ontology.TERMINAL_STATES,
)

IN_DRAFT = Precondition(
    code="NOT_IN_DRAFT",
    description="The request must be in DRAFT.",
    reads=("Request.state",),
    holds=lambda f: f.request["state"] == ontology.DRAFT,
)

AWAITING_DECISION = Precondition(
    code="NOT_AWAITING_DECISION",
    description="The request must be in SUBMITTED, awaiting a decision.",
    reads=("Request.state",),
    holds=lambda f: f.request["state"] == ontology.SUBMITTED,
)

WITHDRAWABLE = Precondition(
    code="NOT_WITHDRAWABLE",
    description="Only a DRAFT or SUBMITTED request can be withdrawn.",
    reads=("Request.state",),
    holds=lambda f: f.request["state"] in (ontology.DRAFT, ontology.SUBMITTED),
)

NOT_SELF_APPROVAL = Precondition(
    code="SELF_APPROVAL",
    description="A principal may not decide a request it raised.",
    reads=("Request.requester_id",),
    holds=lambda f: f.request["requester_id"] != f.principal["person_id"],
)

WITHIN_AUTHORITY = Precondition(
    code="ABOVE_AUTHORITY",
    description=(
        "The request amount must not exceed the principal's authorization "
        "threshold. The amount is read from the store, never from the arguments."
    ),
    reads=("Request.amount_cents", "Person.authority_limit_cents"),
    holds=lambda f: f.request["amount_cents"] <= f.principal["authority_limit_cents"],
)

IS_REQUESTER = Precondition(
    code="NOT_REQUESTER",
    description="Only the principal that raised the request may do this.",
    reads=("Request.requester_id",),
    holds=lambda f: f.request["requester_id"] == f.principal["person_id"],
)

AMOUNT_IN_RANGE = Precondition(
    code="AMOUNT_OUT_OF_RANGE",
    description=f"Amount must be between 1 and {MAX_AMOUNT_CENTS} cents inclusive.",
    reads=("Request.amount_cents",),
    holds=lambda f: 1 <= f.args["amount_cents"] <= MAX_AMOUNT_CENTS,
)

TITLE_PRESENT = Precondition(
    code="TITLE_EMPTY",
    description="A request must carry a non-empty title.",
    reads=("Request.title",),
    holds=lambda f: bool(str(f.args["title"]).strip()),
)

REASON_PRESENT = Precondition(
    code="REASON_EMPTY",
    description="A rejection must carry a non-empty reason.",
    reads=("Request.decision_note",),
    holds=lambda f: bool(str(f.args["reason"]).strip()),
)

ALL = (
    PRINCIPAL_ACTIVE,
    NOT_TERMINAL,
    IN_DRAFT,
    AWAITING_DECISION,
    WITHDRAWABLE,
    NOT_SELF_APPROVAL,
    WITHIN_AUTHORITY,
    IS_REQUESTER,
    AMOUNT_IN_RANGE,
    TITLE_PRESENT,
    REASON_PRESENT,
)

# Codes raised by the action boundary before any precondition is reached.
RESOLUTION_CODES = ("REQUEST_NOT_FOUND", "PRINCIPAL_NOT_FOUND")
ARGUMENT_CODES = ("UNKNOWN_ARGUMENT", "MISSING_ARGUMENT", "ARGUMENT_TYPE")
