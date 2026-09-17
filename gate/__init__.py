"""abyss-write-gate: a deterministic write boundary for an agent with state access.

The package is deliberately small. Read order:

    ontology.py       typed objects, typed properties, typed links
    store.py          the persistence boundary; the only write interface
    preconditions.py  the rules, as data
    actions.py        the only module permitted to open a write context
    agent/            read tools and action-invocation tools
    hostile.py        the deterministic hostile driver
"""

__all__ = ["ontology", "store", "preconditions", "actions"]
