# Lessons

Written as the work happened. Each entry records something that was wrong
first, because an entry that only records what worked teaches the next reader
nothing.

---

## L-001 — `sys._getframe(1)` inside a helper names the helper's caller, not the guard's
**Constraint:** RST-C1

The module guard in `store.py` called `_caller_module(1)` from inside
`action_context`. Depth 1 from inside the helper is `action_context`'s own frame,
so the guard read `gate.store` as the caller and refused the action layer — every
write, including legitimate ones.

What makes it worth recording is how it surfaced: not from reading the code, but
because a direct invocation failed with the guard's own message naming
`gate.store`. A frame-depth error is invisible to inspection and obvious to
execution. Correct depth is 2, and there is now a test that a legitimate action
writes, which is the half that would otherwise be missing — the bypass tests
alone were all still green with the boundary refusing everything.

## L-002 — A two-minute test suite was an fsync problem, not a design problem
**Constraint:** RST-C7

The first full run of the RST-C1 suite did not finish inside two minutes.
Bisecting by test name showed the cost was in the fixture: 10–13 seconds per
seeded world, on a suite where nearly every test builds one.

The instinct was to share a world across tests. That would have coupled the
tests to each other, in a repository whose subject is isolation. Measuring first
gave the real cause — SQLite in autocommit mode fsyncs per statement — and the
fix is two pragmas and a transaction around the seed. 0.08s, and every test
still gets its own database.

The general form: a slow suite is a measurement before it is a design
conclusion.

## L-003 — The first version of the rule-drift scan had a false positive
**Constraint:** RST-C2

The scan asserting that no module outside the rule layer names a rejection code
used `code in text`. It immediately flagged `gate/ontology.py` for
`TERMINAL_STATE` — because the ontology declares the constant `TERMINAL_STATES`,
whose name contains it.

Two things followed. The obvious one: match on whole tokens. The one worth
recording: this fired on the first run, against a clean tree, which is the only
reason it was caught at all. Had the ontology used a different constant name,
the scan would have passed, shipped, and gone off months later against a file
that had done nothing wrong.

A check is not correct because it is green. It is correct when you have seen it
be right about something.

## L-004 — A forbidden-effect predicate matched the world before the case ran
**Constraint:** RST-C4

AC-602 creates a request, submits it, then tries to amend the amount upward to
$48,000. Its forbidden effect was "a request exists with amount 4,800,000 in
state SUBMITTED". The seeded world already contains exactly that: REQ-501. The
case reported `missed` on its first run, and the gate had refused the amendment
correctly.

The bug is not in the gate and not in the driver. It is in the measurement, and
it manufactured a blind spot that did not exist — in a repository whose most
valuable artifact is a published list of blind spots.

The fix is one line in the case data. The check is the part worth keeping: every
forbidden effect is now evaluated against an untouched world, and a case whose
forbidden state is already true fails the suite. An assertion that would pass
against a system that did nothing is not an assertion about that system.
