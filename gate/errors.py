"""Error types for the write boundary.

These are distinct on purpose. A reader should be able to tell, from the
exception type alone, which layer refused.
"""


class WriteBoundaryError(RuntimeError):
    """A write was attempted outside the action layer.

    Raised by the Python guard in store.py before any SQL is issued. The
    database trigger is the backstop for anything that gets past it.
    """


class BootstrapError(RuntimeError):
    """Fixture loading was attempted against a database that is already gated."""


class ActionError(RuntimeError):
    """The action layer was called incorrectly (unknown action, bad arity)."""
