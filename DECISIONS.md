# Build log

Ordered decision records, oldest first. Each record states what was decided and
why. The log is published because the sequence is part of what this repository
demonstrates: nothing here was arrived at by accident, and the order in which
the pieces arrived is legible.

Format is fixed so it can be checked rather than trusted:
`tests/test_rst_c8_build_log.py` asserts that every record carries a timestamp,
a constraint, a decision and a rationale, and that the records are ordered.

---

## DR-001 — The domain is an approval workflow with six actions
**Time:** 2026-09-17T09:40:00-04:00
**Constraint:** RST-C1
**Decision:** Two object types (`Person`, `Request`), two link types (`raised_by`,
`decided_by`), a five-state machine, and six actions: create, submit, amend,
approve, reject, withdraw.
**Rationale:** The preconditions have to be legible without explanation. "An
approver cannot approve their own request" needs no domain briefing; an
equivalent rule in a trading or clinical domain would. Six actions is the
smallest set that still produces a multi-hop laundering surface, which a
three-action set does not.

## DR-002 — Persistence is SQLite from the standard library
**Time:** 2026-09-17T09:48:00-04:00
**Constraint:** RST-C7
**Decision:** One SQLite file, built from `cases/world.json` on every run. No
ORM, no external dependency on the default path.
**Rationale:** RST-C7 requires a clean clone to reach a full adversarial run
with no credential and, in practice, no network. Anything that needs installing
puts a step between the clone and the run. SQLite also supplies the thing the
constraint actually wants: triggers, which enforce the write boundary for any
caller that reaches the connection rather than only for callers that went
through the Python.

## DR-003 — The write boundary is three layers, and each is tested by attempting the bypass
**Time:** 2026-09-17T09:55:00-04:00
**Constraint:** RST-C1
**Decision:** (1) database triggers refuse INSERT/UPDATE on every domain table
unless an action context is open, and refuse DELETE unconditionally; (2)
`Store.action_context` reads its caller's module from the calling frame and
refuses anything but `gate.actions`; (3) a test walks the AST of every module in
the package and asserts none outside the action layer names the write interface.
**Rationale:** A single layer would be satisfied by convention. The database
layer holds against callers this package has never seen; the frame guard holds
against callers inside it; the AST scan makes adding such a caller a test
failure rather than a code review question. Each is tested by performing the
forbidden operation — a check that passes because nobody currently attempts the
thing it forbids has not been shown to detect anything.

## DR-004 — Fixtures load before the gate exists, not through a hole in it
**Time:** 2026-09-17T10:02:00-04:00
**Constraint:** RST-C1
**Decision:** `Store.create` returns an ungated database. Fixtures seed it.
`install_gate` then creates the triggers, and `bootstrap_insert` refuses from
that point on.
**Rationale:** The world contains requests already in terminal states and
principals with thresholds already set — a world no sequence of actions could
produce. The alternatives were a seeding bypass in the action layer, which is
exactly the escape hatch this repository exists to argue against, or fixtures
that cannot express a terminal state, which would delete a whole adversarial
class. Sequencing the gate after the seed costs nothing and leaves no hatch.

## DR-005 — Preconditions are data, and declare which properties they read
**Time:** 2026-09-17T10:08:00-04:00
**Constraint:** RST-C2
**Decision:** Each precondition is a code, a sentence, a tuple of dotted
ontology property references, and a pure predicate. The references are resolved
against the ontology at import time.
**Rationale:** Declared reads make two things checkable that are otherwise
matters of intent: that no rule depends on a model-derived property, and that no
rule reads a property that does not exist. A typo in a rule is then a test
failure rather than a rule that silently never fires.

## DR-006 — Preconditions are evaluated exhaustively, never short-circuited
**Time:** 2026-09-17T10:11:00-04:00
**Constraint:** RST-C2
**Decision:** A rejection names every rule that failed, not the first.
**Rationale:** An adversarial case declares which rejection it expects. If the
boundary short-circuits, that expectation becomes an assertion about evaluation
ORDER, and reordering the rules silently rewrites the expected results of the
case set. Collecting all failures makes the declared expectation stable.

## DR-007 — `synchronous = OFF` on the store connection
**Time:** 2026-09-17T10:14:00-04:00
**Constraint:** RST-C7
**Decision:** The store opens with `journal_mode = MEMORY` and
`synchronous = OFF`.
**Rationale:** Measured, not assumed: with default pragmas the seeded-world
fixture took 10–13 seconds to build on this host, because autocommit fsyncs per
statement. Seventeen tests that each build a world took the suite past two
minutes. With the pragmas the same suite runs in 0.08s. The database is rebuilt
from fixtures on every run and nothing is expected to survive a crash, so
durability buys nothing here and costs the one property RST-C7 cares about:
that a clean clone runs the whole thing quickly enough that a reader actually
does it.

## DR-008 — Rule coverage is asserted, not reviewed
**Time:** 2026-09-17T10:32:00-04:00
**Constraint:** RST-C2
**Decision:** A test derives the set of (action, precondition) pairs from the
registry and asserts that the violation table exercises every one of them.
**Rationale:** The failure mode for a rule table is not a wrong rule, it is a
rule nobody tests, which then stops holding without anything going red. Deriving
the expected set from the registry means adding a precondition without a
violating case is a test failure on the commit that adds it.

## DR-009 — Identifier matches in source scans are whole-token, never substring
**Time:** 2026-09-17T10:38:00-04:00
**Constraint:** RST-C2
**Decision:** The scan asserting that no module re-implements a rejection code
matches on word boundaries.
**Rationale:** The substring form reported `gate/ontology.py` for the rejection
code `TERMINAL_STATE`, because the ontology declares `TERMINAL_STATES`. A check
with a false positive is worse than no check: the next person to hit it turns it
off, and then the true positives go with it.
