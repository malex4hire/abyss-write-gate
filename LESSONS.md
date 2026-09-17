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

## L-005 — "Every case attempted something" was wrong about the case that attempts nothing
**Constraint:** RST-C3

The attempt ledger check asserts that no case passes by doing nothing. It failed
on AC-801, the read-path exfiltration case, which attempts no write — correctly,
because that is the entire class.

The tempting fix is to exempt the case. That would have left a hole shaped
exactly like the failure the check exists to catch: a case that attempts
nothing, passing. The fix that kept the check honest was to require something
else in its place — a read-path case must have a non-empty transcript — so every
case is still required to have done something, and the something is appropriate
to its class.

An exemption with nothing in its place is how a check stops covering the thing
it was written for.

## L-006 — These three fixes were written code-first, and the mutation is what makes them defensible
**Constraint:** RST-C1

The discipline here is failing test, then code, then passing test. DR-021's
three guards did not arrive that way: they came from reading the write
interface back after it was working, and the code was written before the test.

Recording it rather than quietly reordering the commit, because the interesting
part is what stands in for the missing order. Each guard was removed afterwards
and its test run: identity update, atomic forensic record, effect-shape
validation — all three go red without the guard and green with it. That is the
property test-first is a means to, and it is checkable after the fact in a way
that "I wrote the test first" is not.

The order is still the better habit, for a reason this case happens not to
show: a test written after the code tends to test the code that exists rather
than the requirement. The mutation check catches a guard that does nothing. It
does not catch a guard that does the wrong thing confidently.

## L-007 — A green history walk that read nothing looks exactly like a green history walk
**Constraint:** RST-C4

RST-C4 requires that a disposition change carry a decision record in the same
commit. The test walks every commit, diffs the declared dispositions against the
parent, and asserts `DECISIONS.md` was touched where they differ. It passed.

It would also have passed if the function reading dispositions out of a commit
returned nothing at all. No disposition has ever changed in this history, so the
loop body never executes, and a parsing failure inside the walk is
indistinguishable from a clean result.

The fix is one line — assert the walk read the cases it expects before diffing —
and blinding the reader now goes red. The general shape is worth keeping: a test
over a condition that has never occurred needs a separate assertion that it is
looking at real data, or it is measuring its own silence.
