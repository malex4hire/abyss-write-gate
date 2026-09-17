import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gate.fixtures import build_world  # noqa: E402


@pytest.fixture()
def store(tmp_path):
    """A freshly seeded, gated store. One per test; nothing is shared."""
    built = build_world(tmp_path / "gate.db")
    yield built
    built.close()


@pytest.fixture(scope="session")
def hostile_run(tmp_path_factory):
    """One full adversarial run, shared across the assertions made about it.

    Session-scoped because the run is deterministic: every case builds its own
    world, so sharing the RESULT shares no state between tests.
    """
    from gate.runner import execute_run

    return execute_run(tmp_path_factory.mktemp("hostile-run"))
