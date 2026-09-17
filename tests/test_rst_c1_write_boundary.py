"""RST-C1 -- Actions are the only write path.

Each layer is tested by ATTEMPTING the bypass. A check that passes only because
no current caller attempts the thing it forbids proves nothing, so every test
here performs the forbidden operation itself.
"""

from __future__ import annotations

import ast
import sqlite3
from pathlib import Path

import pytest

from gate import actions, ontology
from gate.errors import BootstrapError, WriteBoundaryError
from gate.store import ACTION_LAYER, Store

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "gate"

# The names that constitute the write interface. A module outside the action
# layer that mentions any of these is a finding, whatever it does with them.
WRITE_INTERFACE_NAMES = frozenset(
    {"action_context", "ActionContext", "bootstrap_insert", "install_gate"}
)

# store.py defines the interface; actions.py is the action layer; fixtures.py
# is the pre-gate bootstrap and is allowed the bootstrap names only.
_DEFINING_MODULES = {"gate/store.py"}
_ACTION_MODULES = {"gate/actions.py"}
_BOOTSTRAP_MODULES = {"gate/fixtures.py"}
_BOOTSTRAP_NAMES = frozenset({"bootstrap_insert", "install_gate"})


# --- layer 1: the database -------------------------------------------------


def test_raw_update_outside_an_action_context_is_refused_by_the_database(store):
    """The persistence boundary refuses, not the caller."""
    with pytest.raises(sqlite3.IntegrityError) as excinfo:
        store.connection().execute(
            "UPDATE requests SET state = 'APPROVED' WHERE request_id = 'REQ-501'"
        )
    assert "WRITE_OUTSIDE_ACTION" in str(excinfo.value)
    assert store.get("Request", "REQ-501")["state"] == ontology.SUBMITTED


def test_raw_insert_outside_an_action_context_is_refused_by_the_database(store):
    before = store.count("Request")
    with pytest.raises(sqlite3.IntegrityError) as excinfo:
        store.connection().execute(
            "INSERT INTO requests (request_id, title, amount_cents, state, "
            "justification, requester_id) VALUES "
            "('REQ-999', 'smuggled', 1, 'DRAFT', '', 'eli')"
        )
    assert "WRITE_OUTSIDE_ACTION" in str(excinfo.value)
    assert store.count("Request") == before


def test_delete_is_refused_unconditionally_even_inside_an_action_context(store):
    """No hard deletes. Rejected attempts stay on disk as forensic records."""
    with pytest.raises(sqlite3.IntegrityError) as excinfo:
        store.connection().execute("DELETE FROM requests WHERE request_id = 'REQ-501'")
    assert "HARD_DELETE_FORBIDDEN" in str(excinfo.value)
    assert store.get("Request", "REQ-501") is not None


def test_the_forensic_log_cannot_be_rewritten(store):
    actions.invoke(store, "dana", "approve_request", {"request_id": "REQ-502"})
    with pytest.raises(sqlite3.IntegrityError) as excinfo:
        store.connection().execute("UPDATE action_log SET outcome = 'APPLIED'")
    assert "FORENSIC_APPEND_ONLY" in str(excinfo.value)
    with pytest.raises(sqlite3.IntegrityError):
        store.connection().execute("DELETE FROM action_log")
    assert len(store.attempts()) == 1


def test_every_domain_table_carries_the_gate_triggers(store):
    names = {
        row["name"]
        for row in store.query(
            "SELECT name FROM sqlite_master WHERE type = 'trigger'"
        )
    }
    for table in ontology.domain_tables():
        for verb in ("insert", "update", "delete"):
            assert f"gate_{table}_{verb}" in names


# --- layer 2: the python guard ---------------------------------------------


def test_opening_an_action_context_from_outside_the_action_layer_is_refused(store):
    """This test module is not the action layer, and asks anyway."""
    with pytest.raises(WriteBoundaryError) as excinfo:
        store.action_context("approve_request", "dana")
    assert "WRITE_OUTSIDE_ACTION" in str(excinfo.value)
    assert __name__ not in ACTION_LAYER


def test_the_guard_reads_the_calling_frame_not_an_argument(store):
    """A caller cannot claim to be the action layer: there is no parameter for it."""
    import inspect

    signature = inspect.signature(Store.action_context)
    assert list(signature.parameters) == ["self", "action", "principal_id"]


def test_bootstrap_is_refused_once_the_gate_is_installed(store):
    with pytest.raises(BootstrapError):
        store.bootstrap_insert(
            "Person",
            {
                "person_id": "intruder",
                "display_name": "Intruder",
                "role": "manager",
                "authority_limit_cents": 100000000,
                "active": 1,
            },
        )
    assert store.get("Person", "intruder") is None


def test_a_seeded_world_is_always_gated(store):
    assert store.is_gated()


def test_an_unseeded_store_is_not_gated_until_it_is(tmp_path):
    raw = Store.create(tmp_path / "raw.db")
    assert not raw.is_gated()
    raw.install_gate()
    assert raw.is_gated()
    raw.close()


# --- layer 3: the source tree ----------------------------------------------


def _package_modules() -> list[Path]:
    return sorted(p for p in PACKAGE.rglob("*.py"))


def _names_used(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    used: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            used.add(node.attr)
        elif isinstance(node, ast.alias):
            used.add(node.asname or node.name.rsplit(".", 1)[-1])
    return used


def test_no_module_outside_the_action_layer_names_the_write_interface():
    offenders = {}
    for path in _package_modules():
        rel = path.relative_to(ROOT).as_posix()
        if rel in _DEFINING_MODULES or rel in _ACTION_MODULES:
            continue
        allowed = _BOOTSTRAP_NAMES if rel in _BOOTSTRAP_MODULES else frozenset()
        hits = (_names_used(path) & WRITE_INTERFACE_NAMES) - allowed
        if hits:
            offenders[rel] = sorted(hits)
    assert offenders == {}, f"write interface referenced outside the action layer: {offenders}"


def test_the_ast_check_actually_catches_a_planted_violation(tmp_path):
    """Mutate the CHECK, not only the subject.

    A source scan that passes because the tree happens to be clean has not been
    shown to detect anything. Plant the violation and require a hit.
    """
    planted = tmp_path / "rogue.py"
    planted.write_text(
        "from gate.store import Store\n"
        "def smuggle(store):\n"
        "    with store.action_context('approve_request', 'dana') as ctx:\n"
        "        ctx.update('Request', 'REQ-501', {'state': 'APPROVED'})\n",
        encoding="utf-8",
    )
    assert _names_used(planted) & WRITE_INTERFACE_NAMES == {"action_context"}


def test_the_action_layer_is_exactly_one_module():
    assert ACTION_LAYER == frozenset({"gate.actions"})
    assert actions.__name__ in ACTION_LAYER


def test_the_action_layer_is_the_only_module_that_opens_a_context():
    source = (PACKAGE / "actions.py").read_text(encoding="utf-8")
    assert "store.action_context(" in source
    for path in _package_modules():
        rel = path.relative_to(ROOT).as_posix()
        if rel in _ACTION_MODULES or rel in _DEFINING_MODULES:
            continue
        assert "action_context(" not in path.read_text(encoding="utf-8"), rel


# --- the action layer still works ------------------------------------------


def test_an_action_writes_through_the_context_and_lands(store):
    result = actions.invoke(store, "priya", "approve_request", {"request_id": "REQ-501"})
    assert result.applied
    row = store.get("Request", "REQ-501")
    assert row["state"] == ontology.APPROVED
    assert row["decided_by_id"] == "priya"


def test_a_rejected_action_leaves_the_row_untouched(store):
    before = dict(store.get("Request", "REQ-501"))
    result = actions.invoke(store, "dana", "approve_request", {"request_id": "REQ-501"})
    assert not result.applied
    assert "ABOVE_AUTHORITY" in result.rejection_codes
    assert dict(store.get("Request", "REQ-501")) == before


def test_the_schema_is_generated_from_the_ontology(store):
    for obj in ontology.OBJECT_TYPES:
        columns = {
            row["name"]
            for row in store.query(f"PRAGMA table_info({obj.table})")
        }
        assert columns == {p.name for p in obj.properties}
