"""Loading the synthetic world.

Fixtures describe a world that already exists: requests sitting in terminal
states, principals with thresholds already set. No sequence of actions could
produce that world, so seeding does not run through the action layer -- it runs
BEFORE the gate exists, and the gate is installed on the way out.

That ordering is the whole trick, and it is checked from both ends:
``bootstrap_insert`` refuses once the gate is installed, and ``build_world``
always returns a gated store.
"""

from __future__ import annotations

import json
from pathlib import Path

from .store import Store

WORLD_PATH = Path(__file__).resolve().parent.parent / "cases" / "world.json"


def load_world(path: Path | str | None = None) -> dict:
    with open(path or WORLD_PATH, encoding="utf-8") as handle:
        return json.load(handle)


def build_world(db_path: Path | str, world: dict | None = None) -> Store:
    """Create a fresh database, seed it, then close the door behind us."""
    world = world if world is not None else load_world()
    store = Store.create(db_path)
    conn = store.connection()
    conn.execute("BEGIN")
    for person in world["people"]:
        store.bootstrap_insert("Person", person)
    for request in world["requests"]:
        store.bootstrap_insert("Request", request)
    conn.execute("COMMIT")
    store.install_gate()
    return store
