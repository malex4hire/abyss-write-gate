"""The persistence boundary.

Three independent layers stand between a caller and a row.

  1. DATABASE. Every domain table carries BEFORE INSERT / BEFORE UPDATE
     triggers that abort unless an action context is open, and a BEFORE DELETE
     trigger that aborts unconditionally. This holds for any caller that
     reaches the connection, including raw SQL from outside this package.

  2. PYTHON. ``Store.action_context`` -- the only way to open one -- inspects
     its caller's module and refuses anything that is not the action layer. The
     check runs before any SQL is issued.

  3. SOURCE TREE. ``tests/test_rst_c1_write_boundary.py`` walks the AST of every
     module in this package and asserts that no module outside the action layer
     so much as names the write interface.

Each layer is tested by attempting the bypass, not by observing that nobody
currently attempts it.

What this does NOT prove is stated plainly in the README: a caller holding the
connection could forge the context row in SQL. Layer 2 makes that unreachable
from inside the package and layer 3 makes adding such a caller a test failure,
but the database alone does not distinguish a forged context from a real one.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from . import ontology
from .errors import BootstrapError, WriteBoundaryError

# The action layer. Exactly one module, named here and nowhere else.
ACTION_LAYER = frozenset({"gate.actions"})

WRITE_REFUSED = "WRITE_OUTSIDE_ACTION"
DELETE_REFUSED = "HARD_DELETE_FORBIDDEN"

_CONTEXT_TABLE = "gate_context"

ACTION_LOG_DDL = """
CREATE TABLE action_log (
    seq             INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id         TEXT,
    principal_id    TEXT NOT NULL,
    action          TEXT NOT NULL,
    args_json       TEXT NOT NULL,
    via             TEXT NOT NULL,
    outcome         TEXT NOT NULL,
    rejection_codes TEXT NOT NULL,
    message         TEXT NOT NULL
)
"""

CONTEXT_DDL = f"""
CREATE TABLE {_CONTEXT_TABLE} (
    id           INTEGER PRIMARY KEY CHECK (id = 1),
    action       TEXT,
    principal_id TEXT,
    token        TEXT
)
"""


def _connect(path: Path) -> sqlite3.Connection:
    """Open the database in autocommit mode with the gate's pragmas.

    ``synchronous = OFF`` is deliberate and safe here: this database is rebuilt
    from ``cases/world.json`` on every run and nothing is expected to survive a
    crash. Leaving it on costs an fsync per statement, which on some hosts is
    the difference between a two-second suite and a two-minute one.
    """
    conn = sqlite3.connect(str(path), isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = MEMORY")
    conn.execute("PRAGMA synchronous = OFF")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _caller_module(depth: int) -> str:
    return sys._getframe(depth).f_globals.get("__name__", "<unknown>")


def _schema_statements() -> list[str]:
    """CREATE TABLE statements derived from the ontology, in declaration order."""
    statements = []
    for obj in ontology.OBJECT_TYPES:
        columns = [p.sql_column(is_key=(p.name == obj.key)) for p in obj.properties]
        for link in ontology.LINK_TYPES:
            if link.source != obj.name:
                continue
            target = ontology.object_type(link.target)
            columns.append(
                f"FOREIGN KEY ({link.column}) REFERENCES {target.table}({target.key})"
            )
        body = ",\n    ".join(columns)
        statements.append(f"CREATE TABLE {obj.table} (\n    {body}\n)")
    return statements


def _gate_statements() -> list[str]:
    """The triggers. One pair per domain table, plus the append-only forensics."""
    open_ctx = f"(SELECT token FROM {_CONTEXT_TABLE} WHERE id = 1) IS NULL"
    statements = []
    for table in ontology.domain_tables():
        statements.append(
            f"CREATE TRIGGER gate_{table}_insert BEFORE INSERT ON {table}\n"
            f"WHEN {open_ctx}\n"
            f"BEGIN SELECT RAISE(ABORT, '{WRITE_REFUSED}: INSERT on {table}'); END"
        )
        statements.append(
            f"CREATE TRIGGER gate_{table}_update BEFORE UPDATE ON {table}\n"
            f"WHEN {open_ctx}\n"
            f"BEGIN SELECT RAISE(ABORT, '{WRITE_REFUSED}: UPDATE on {table}'); END"
        )
        statements.append(
            f"CREATE TRIGGER gate_{table}_delete BEFORE DELETE ON {table}\n"
            f"BEGIN SELECT RAISE(ABORT, '{DELETE_REFUSED}: DELETE on {table}'); END"
        )
    statements.append(
        "CREATE TRIGGER gate_action_log_update BEFORE UPDATE ON action_log\n"
        "BEGIN SELECT RAISE(ABORT, 'FORENSIC_APPEND_ONLY: UPDATE on action_log'); END"
    )
    statements.append(
        "CREATE TRIGGER gate_action_log_delete BEFORE DELETE ON action_log\n"
        "BEGIN SELECT RAISE(ABORT, 'FORENSIC_APPEND_ONLY: DELETE on action_log'); END"
    )
    return statements


class ActionContext:
    """An open write window. Only ``gate.actions`` can obtain one."""

    def __init__(self, store: "Store", action: str, principal_id: str, token: str):
        self._store = store
        self.action = action
        self.principal_id = principal_id
        self.token = token
        self._open = False

    def __enter__(self) -> "ActionContext":
        conn = self._store._conn
        conn.execute("BEGIN")
        conn.execute(
            f"UPDATE {_CONTEXT_TABLE} SET action = ?, principal_id = ?, token = ? "
            "WHERE id = 1",
            (self.action, self.principal_id, self.token),
        )
        self._open = True
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        conn = self._store._conn
        conn.execute(
            f"UPDATE {_CONTEXT_TABLE} SET action = NULL, principal_id = NULL, "
            "token = NULL WHERE id = 1"
        )
        if exc_type is None:
            conn.execute("COMMIT")
        else:
            conn.execute("ROLLBACK")
        self._open = False
        return False

    def _require_open(self) -> None:
        if not self._open:
            raise WriteBoundaryError("action context is not open")

    def insert(self, type_name: str, values: Mapping[str, Any]) -> None:
        self._require_open()
        obj = ontology.object_type(type_name)
        row = _validated_row(obj, values, full=True)
        cols = ", ".join(row)
        marks = ", ".join("?" for _ in row)
        self._store._conn.execute(
            f"INSERT INTO {obj.table} ({cols}) VALUES ({marks})", tuple(row.values())
        )

    def update(self, type_name: str, key: str, changes: Mapping[str, Any]) -> None:
        self._require_open()
        obj = ontology.object_type(type_name)
        row = _validated_row(obj, changes, full=False)
        assignments = ", ".join(f"{name} = ?" for name in row)
        self._store._conn.execute(
            f"UPDATE {obj.table} SET {assignments} WHERE {obj.key} = ?",
            (*row.values(), key),
        )


def _validated_row(
    obj: ontology.ObjectType, values: Mapping[str, Any], full: bool
) -> dict[str, Any]:
    unknown = sorted(set(values) - {p.name for p in obj.properties})
    if unknown:
        raise WriteBoundaryError(f"{obj.name}: unknown properties {unknown}")
    if full:
        missing = [
            p.name
            for p in obj.properties
            if not p.nullable and p.name not in values
        ]
        if missing:
            raise WriteBoundaryError(f"{obj.name}: missing properties {missing}")
    out: dict[str, Any] = {}
    for name, value in values.items():
        prop = obj.prop(name)
        if prop.datatype == "enum" and value not in prop.values:
            raise WriteBoundaryError(f"{obj.name}.{name}: {value!r} is not a declared value")
        if prop.datatype == "bool":
            value = int(bool(value))
        out[name] = value
    return out


class Store:
    """A SQLite-backed object store with a gated write path."""

    def __init__(self, conn: sqlite3.Connection, path: Path):
        self._conn = conn
        self.path = path
        self._token_seq = 0

    # ---- construction -----------------------------------------------------

    @classmethod
    def create(cls, path: str | Path) -> "Store":
        """Create an empty, UNGATED database. Fixtures load into this."""
        path = Path(path)
        if path.exists():
            path.unlink()
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = _connect(path)
        for statement in _schema_statements():
            conn.execute(statement)
        conn.execute(ACTION_LOG_DDL)
        conn.execute(CONTEXT_DDL)
        conn.execute(
            f"INSERT INTO {_CONTEXT_TABLE} (id, action, principal_id, token) "
            "VALUES (1, NULL, NULL, NULL)"
        )
        return cls(conn, path)

    @classmethod
    def open(cls, path: str | Path) -> "Store":
        path = Path(path)
        store = cls(_connect(path), path)
        if not store.is_gated():
            raise BootstrapError(f"{path} has no gate installed")
        return store

    def is_gated(self) -> bool:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM sqlite_master "
            "WHERE type = 'trigger' AND name LIKE 'gate_%'"
        ).fetchone()
        return row["n"] > 0

    def install_gate(self) -> None:
        """Close the bootstrap door. After this, writes need an action context."""
        if self.is_gated():
            return
        for statement in _gate_statements():
            self._conn.execute(statement)

    def bootstrap_insert(self, type_name: str, values: Mapping[str, Any]) -> None:
        """Seed a fixture row. Refused once the gate is installed.

        Fixtures describe a world that already exists -- requests in terminal
        states, principals with histories -- which no sequence of actions could
        produce. They load before the gate, never through a hole in it.
        """
        if self.is_gated():
            raise BootstrapError(
                "bootstrap_insert refused: the gate is installed on this database"
            )
        obj = ontology.object_type(type_name)
        row = _validated_row(obj, values, full=True)
        cols = ", ".join(row)
        marks = ", ".join("?" for _ in row)
        self._conn.execute(
            f"INSERT INTO {obj.table} ({cols}) VALUES ({marks})", tuple(row.values())
        )

    # ---- reads ------------------------------------------------------------

    def connection(self) -> sqlite3.Connection:
        """The live connection. Reads freely; writes meet the triggers."""
        return self._conn

    def query(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        return list(self._conn.execute(sql, tuple(params)).fetchall())

    def get(self, type_name: str, key: str) -> dict[str, Any] | None:
        obj = ontology.object_type(type_name)
        row = self._conn.execute(
            f"SELECT * FROM {obj.table} WHERE {obj.key} = ?", (key,)
        ).fetchone()
        return dict(row) if row is not None else None

    def all(self, type_name: str) -> list[dict[str, Any]]:
        obj = ontology.object_type(type_name)
        rows = self._conn.execute(
            f"SELECT * FROM {obj.table} ORDER BY {obj.key}"
        ).fetchall()
        return [dict(r) for r in rows]

    def count(self, type_name: str, **where: Any) -> int:
        obj = ontology.object_type(type_name)
        clause = " AND ".join(f"{k} = ?" for k in where) or "1 = 1"
        row = self._conn.execute(
            f"SELECT COUNT(*) AS n FROM {obj.table} WHERE {clause}",
            tuple(where.values()),
        ).fetchone()
        return int(row["n"])

    # ---- the write interface ---------------------------------------------

    def action_context(self, action: str, principal_id: str) -> ActionContext:
        """Open a write window. Callable only from the action layer.

        The caller's module is read from the calling frame, not passed in, so
        there is nothing for a caller to assert about itself.
        """
        # depth 2: this frame's caller, not _caller_module's.
        caller = _caller_module(2)
        if caller not in ACTION_LAYER:
            raise WriteBoundaryError(
                f"{WRITE_REFUSED}: {caller!r} may not open an action context; "
                f"the action layer is {sorted(ACTION_LAYER)}"
            )
        self._token_seq += 1
        return ActionContext(self, action, principal_id, f"ctx-{self._token_seq:04d}")

    # ---- forensics --------------------------------------------------------

    def record_attempt(
        self,
        *,
        case_id: str | None,
        principal_id: str,
        action: str,
        args: Mapping[str, Any],
        via: str,
        outcome: str,
        rejection_codes: Iterable[str] = (),
        message: str = "",
    ) -> int:
        """Append one row per attempt. Never updated, never deleted.

        Rejected attempts are retained: a refusal that logs nothing makes the
        next occurrence cost what this one did.
        """
        cur = self._conn.execute(
            "INSERT INTO action_log (case_id, principal_id, action, args_json, via, "
            "outcome, rejection_codes, message) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                case_id,
                principal_id,
                action,
                json.dumps(args, sort_keys=True, default=str),
                via,
                outcome,
                ",".join(sorted(rejection_codes)),
                message,
            ),
        )
        return int(cur.lastrowid)

    def attempts(self, case_id: str | None = None) -> list[dict[str, Any]]:
        if case_id is None:
            rows = self._conn.execute("SELECT * FROM action_log ORDER BY seq").fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM action_log WHERE case_id = ? ORDER BY seq", (case_id,)
            ).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        self._conn.close()
