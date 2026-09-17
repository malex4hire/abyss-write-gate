"""Verification of the PUBLISHED surface -- what an unauthenticated visitor sees.

Deliberately outside the `gate` package. `make demo` is standard-library-only
and opens no socket, and that is asserted; this opens sockets by definition, so
it lives somewhere the gate's default path cannot reach and a test says so.
"""
