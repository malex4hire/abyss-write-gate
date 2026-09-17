"""The ontology: typed objects, typed properties, typed links.

Two things here are load-bearing rather than decorative.

1. PROVENANCE. Every property declares whether it is ``MEASURED`` (recorded by
   a system of record, a fact) or ``MODEL_DERIVED`` (produced by a language
   model, a proposal). No precondition may read a MODEL_DERIVED
   property. A gate that can be moved by model output is not a gate, and
   ``tests/test_rst_c2_preconditions.py`` asserts the separation both from the
   declared reads and from the source tree.

2. THE SCHEMA IS GENERATED FROM THIS FILE. ``store.py`` builds its CREATE TABLE
   statements from these declarations, so the ontology and the tables cannot
   drift apart. Adding a property here adds a column; there is no second place
   to edit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

MEASURED = "measured"
MODEL_DERIVED = "model_derived"
PROVENANCES = (MEASURED, MODEL_DERIVED)

# Request states. The first three are working states; the last three are
# terminal and nothing transitions out of them.
DRAFT = "DRAFT"
SUBMITTED = "SUBMITTED"
APPROVED = "APPROVED"
REJECTED = "REJECTED"
WITHDRAWN = "WITHDRAWN"

REQUEST_STATES = (DRAFT, SUBMITTED, APPROVED, REJECTED, WITHDRAWN)
TERMINAL_STATES = frozenset({APPROVED, REJECTED, WITHDRAWN})


@dataclass(frozen=True)
class Property:
    name: str
    datatype: str  # "text" | "int" | "bool" | "enum"
    provenance: str
    values: tuple[str, ...] = ()
    nullable: bool = False
    doc: str = ""

    def __post_init__(self) -> None:
        if self.provenance not in PROVENANCES:
            raise ValueError(f"unknown provenance {self.provenance!r}")
        if self.datatype == "enum" and not self.values:
            raise ValueError(f"enum property {self.name!r} declares no values")

    @property
    def sql_type(self) -> str:
        return {"text": "TEXT", "int": "INTEGER", "bool": "INTEGER", "enum": "TEXT"}[
            self.datatype
        ]

    def sql_column(self, is_key: bool) -> str:
        parts = [self.name, self.sql_type]
        if is_key:
            parts.append("PRIMARY KEY")
        elif not self.nullable:
            parts.append("NOT NULL")
        if self.datatype == "enum":
            allowed = ", ".join(f"'{v}'" for v in self.values)
            parts.append(f"CHECK ({self.name} IN ({allowed}))")
        return " ".join(parts)


@dataclass(frozen=True)
class ObjectType:
    name: str
    table: str
    key: str
    properties: tuple[Property, ...]
    doc: str = ""
    _by_name: Mapping[str, Property] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_by_name", {p.name: p for p in self.properties})
        if self.key not in self._by_name:
            raise ValueError(f"{self.name}: key {self.key!r} is not a declared property")

    def prop(self, name: str) -> Property:
        return self._by_name[name]

    def has(self, name: str) -> bool:
        return name in self._by_name

    @property
    def measured(self) -> tuple[Property, ...]:
        return tuple(p for p in self.properties if p.provenance == MEASURED)

    @property
    def model_derived(self) -> tuple[Property, ...]:
        return tuple(p for p in self.properties if p.provenance == MODEL_DERIVED)


@dataclass(frozen=True)
class LinkType:
    """A typed edge, stored as a column on the source object's table."""

    name: str
    source: str
    target: str
    column: str
    required: bool
    doc: str = ""


PERSON = ObjectType(
    name="Person",
    table="people",
    key="person_id",
    doc="A principal that can raise or decide requests. Synthetic; no real people.",
    properties=(
        Property("person_id", "text", MEASURED, doc="Stable identifier."),
        Property("display_name", "text", MEASURED, doc="Name as shown in tools."),
        Property("role", "text", MEASURED, doc="Org role. Descriptive only."),
        Property(
            "authority_limit_cents",
            "int",
            MEASURED,
            doc="Maximum request amount this principal may approve, in cents.",
        ),
        Property(
            "active",
            "bool",
            MEASURED,
            doc="0 for a deactivated principal. Inactive principals decide nothing.",
        ),
    ),
)

REQUEST = ObjectType(
    name="Request",
    table="requests",
    key="request_id",
    doc="A spend approval request moving through a five-state machine.",
    properties=(
        Property("request_id", "text", MEASURED, doc="Stable identifier."),
        Property("title", "text", MEASURED, doc="Short human label."),
        Property("amount_cents", "int", MEASURED, doc="Requested amount, in cents."),
        Property(
            "state",
            "enum",
            MEASURED,
            values=REQUEST_STATES,
            doc="Workflow state. APPROVED, REJECTED and WITHDRAWN are terminal.",
        ),
        Property(
            "justification",
            "text",
            MEASURED,
            doc=(
                "Free text supplied by the requester. This is the untrusted "
                "surface: it reaches the agent verbatim through read tools."
            ),
        ),
        Property(
            "decision_note",
            "text",
            MEASURED,
            nullable=True,
            doc="Free text recorded by whoever decided the request.",
        ),
        Property(
            "risk_summary",
            "text",
            MODEL_DERIVED,
            nullable=True,
            doc=(
                "A model's one-line read of the request. Shown to the agent, "
                "readable by no precondition. Marked model-derived precisely so "
                "that the separation is checkable rather than remembered."
            ),
        ),
        Property("requester_id", "text", MEASURED, doc="Link column for raised_by."),
        Property(
            "decided_by_id",
            "text",
            MEASURED,
            nullable=True,
            doc="Link column for decided_by.",
        ),
    ),
)

OBJECT_TYPES = (PERSON, REQUEST)

RAISED_BY = LinkType(
    name="raised_by",
    source="Request",
    target="Person",
    column="requester_id",
    required=True,
    doc="Every request is raised by exactly one principal.",
)

DECIDED_BY = LinkType(
    name="decided_by",
    source="Request",
    target="Person",
    column="decided_by_id",
    required=False,
    doc="A decided request records the principal that decided it.",
)

LINK_TYPES = (RAISED_BY, DECIDED_BY)

_BY_NAME = {o.name: o for o in OBJECT_TYPES}
_BY_TABLE = {o.table: o for o in OBJECT_TYPES}


def object_type(name: str) -> ObjectType:
    return _BY_NAME[name]


def object_type_for_table(table: str) -> ObjectType:
    return _BY_TABLE[table]


def domain_tables() -> tuple[str, ...]:
    return tuple(o.table for o in OBJECT_TYPES)


def resolve_property(ref: str) -> Property:
    """Resolve a dotted property reference such as ``Request.amount_cents``.

    Raises KeyError if the reference names nothing in the ontology. Preconditions
    declare their reads using these references, so a typo is a test failure
    rather than a silently unchecked rule.
    """
    obj_name, _, prop_name = ref.partition(".")
    if not prop_name:
        raise KeyError(f"malformed property reference {ref!r}")
    obj = _BY_NAME[obj_name]
    if not obj.has(prop_name):
        raise KeyError(f"{obj_name} has no property {prop_name!r}")
    return obj.prop(prop_name)
