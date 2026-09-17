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

## DR-010 — The adversarial set is data; the class list is code
**Time:** 2026-09-17T10:52:00-04:00
**Constraint:** RST-C4
**Decision:** Cases live in `cases/adversarial/*.json`, one file per class. The
required class list lives in `gate/cases.py` and a test asserts every entry has
at least one case. No module names a case.
**Rationale:** Splitting it this way makes the two failure modes fail
differently. Adding a case is a data change with no code review surface, which
is what keeps the set growable. A class QUIETLY DISAPPEARING from the data is a
test failure, because the expectation lives somewhere the data cannot edit. A
test asserts no module hardcodes a case identifier, so the driver cannot grow a
special case for a case.

## DR-011 — `gated` partitions the set, and reconciles RST-C3 with RST-C5
**Time:** 2026-09-17T10:58:00-04:00
**Constraint:** RST-C4
**Decision:** Every case declares `gated`. A gated case is one whose attempted
action violates a declared precondition; it must be caught. An ungated case
violates no precondition; it lands, and it is a register entry. The loader
refuses any case where `gated` and `expected_disposition` disagree.
**Rationale:** RST-C3 requires that nothing forbidden lands. RST-C5 requires a
non-empty missed set. Read loosely those contradict, and the temptation is to
resolve it by quietly weakening one. They are not in tension once "forbidden" is
defined: a forbidden write is one that violates a rule the gate declares, and
none of those land. The misses are writes no rule covers — which is a statement
about the ontology, not about the enforcement. Making the partition a required
field means the distinction is in the data rather than in a paragraph someone
has to remember.

## DR-012 — A forbidden effect must be false before the case runs
**Time:** 2026-09-17T11:04:00-04:00
**Constraint:** RST-C4
**Decision:** A test evaluates every case's `forbidden_effect` against a freshly
seeded world with no steps executed, and fails if any is already true.
**Rationale:** Found by building it wrong. AC-602's forbidden effect matched any
$48,000 request in SUBMITTED, and the seeded world contains one, so the case
reported `missed` regardless of what the gate did. The failure is silent in the
worst direction: it manufactures a fake blind spot, and a register entry that is
not real is worse than a missing one, because it is published.

## DR-013 — Every case runs against its own freshly seeded database
**Time:** 2026-09-17T11:12:00-04:00
**Constraint:** RST-C3
**Decision:** `HostileDriver.run_case` builds a new world per case, in
`<run>/cases/<case-id>.db`, and every database is retained after the run.
**Rationale:** A shared datastore makes a disposition depend on ordering.
AC-603's forbidden effect is an aggregate over everything the principal has
approved, so a case that ran earlier and approved something legitimately would
contaminate it. Isolation makes each verdict a property of the case. Retaining
the databases is the forensic half: a rejected attempt is a record, and keeping
it means a reader can open the file and check the claim rather than take the
summary's word.

## DR-014 — The hostile driver has no refusal path
**Time:** 2026-09-17T11:18:00-04:00
**Constraint:** RST-C3
**Decision:** The driver is deterministic, executes every step, and executes
every instruction it finds in tool output. There is no branch in it that
declines.
**Rationale:** A model adversary would decline sometimes, and then a green run
is evidence about the model's disposition rather than about the gate. Maximal
credulity makes the driver a stronger adversary than the thing it replaces, and
it makes every result in this repository reproducible by anyone with a clone and
no credential. The cost is that the injection format is synthetic — a marker and
a JSON payload — which is stated in the module rather than hidden.

## DR-015 — The register embeds its own counts, machine-readable
**Time:** 2026-09-17T11:34:00-04:00
**Constraint:** RST-C5
**Decision:** `RunResult.counts()` computes every published number exactly once.
The register renders them into prose and into a fenced JSON block, and a test
parses the block and compares it to the run.
**Rationale:** RST-C5 requires that every count in the document match the count
computed from the run. Asserting that against prose means parsing English. A
machine-readable block makes the assertion exact, and rendering both from one
dictionary means the prose and the block cannot drift — there is no second place
where a number is decided. The counts are also mutated: dropping a case from the
run must move them, which is what distinguishes a derived number from a typed
one.

## DR-016 — The README artifact carries no volatile field at all
**Time:** 2026-09-17T11:40:00-04:00
**Constraint:** RST-C6
**Decision:** The SVG contains no timestamp, no duration, no path and no port.
Regeneration is asserted by byte equality, and a second test asserts the
volatile normaliser changes nothing in it.
**Rationale:** The allowlist permits volatile fields; producing none is
strictly stronger, and it removes the way this assertion usually rots — an
equivalence check whose normaliser quietly grows until it is comparing almost
nothing. The paired test is the guard: byte equality is only meaningful once you
have shown that nothing volatile was excluded from the comparison.

## DR-017 — The artifact selects its case from the data
**Time:** 2026-09-17T11:44:00-04:00
**Constraint:** RST-C6
**Decision:** The renderer takes the first gated case of a named class rather
than a named case identifier. Every value on the panel — amount, threshold,
rejection code, message, state afterwards — is read out of the run it performs.
**Rationale:** The test forbidding any module from hardcoding a case identifier
caught the first version, which named `AC-101`. The exemption was available and
would have been reasonable-sounding. Selecting from the data instead makes the
picture a view onto the case set rather than a second story about it, and means
the panel cannot show something the suite is not also asserting.

## DR-018 — The default path has no provider, and nothing is structured to need one
**Time:** 2026-09-17T11:52:00-04:00
**Constraint:** RST-C7
**Decision:** `make demo` runs the whole set with the standard library, reading
no credential and making no network call. The hostile driver is an ordinary
object constructed by the runner, so a live-provider driver could be added
beside it later without the default path changing.
**Rationale:** A demonstration whose results a reader cannot reproduce is an
assertion with a screenshot attached. Determinism is what makes the published
register checkable rather than believable, so the deterministic driver is the
default and not a fallback. Keeping the driver behind one seam is what leaves a
live mode possible without inviting it into the gating set — a model-driven run
would be a development aid, and a development aid does not get to decide whether
the suite is green.

## DR-019 — The build log has a fixed format so it can be checked
**Time:** 2026-09-17T12:06:00-04:00
**Constraint:** RST-C8
**Decision:** Each record is `## DR-NNN — title` followed by `**Time:**`,
`**Constraint:**`, `**Decision:**` and `**Rationale:**`. A test parses them and
asserts the numbering has no gap, the timestamps are real and in order, every
record names a constraint, and every constraint has at least one record.
**Rationale:** A build log published as evidence is a deliverable, and a
deliverable gets a gate like everything else here. The specific thing worth
catching is a record with a decision and no reason, which is the shape a log
degrades into: still ordered, still timestamped, no longer explaining anything.

## DR-020 — Pace is inferred from the log; the README claims nothing about it
**Time:** 2026-09-17T12:10:00-04:00
**Constraint:** RST-C8
**Decision:** No elapsed-time claim appears in the README, and a test asserts it
against ten phrasings — paired with a test that the same check does not fire on
ordinary prose.
**Rationale:** Every claim in this repository names the gate that proves it, and
no gate can prove elapsed time. A decision log with ordered timestamps is
evidence and needs no claim attached; a reader who cares can read the sequence
and draw their own conclusion, which is worth more than a sentence asserting it.
The false-positive half of the test is not decoration: a check that flags
"a five-state machine" would be disabled by the next person to hit it, and the
true positives would go with it.

## DR-021 — Three gaps closed by reading the write interface back
**Time:** 2026-09-17T12:38:00-04:00
**Constraint:** RST-C1
**Decision:** An action context refuses to update an object's key; the forensic
record for an applied action commits inside the same transaction as the
mutation; and the case loader validates the shape of every `forbidden_effect`.
**Rationale:** None of the three was reachable from the adversarial set, which
is exactly why they are worth naming. An identity update is a substitution that
silently detaches every link pointing at the old key. A forensic record written
after the commit means a landed write with no row in the ledger is a state the
system can reach — in an append-only log whose whole purpose is that it cannot.
A malformed effect surfaces as a `KeyError` mid-run, by which time the case has
already been reported as something. Each guard was verified by removing it and
watching the test go red.

## DR-022 — Two assertions that could have passed having checked nothing
**Time:** 2026-09-17T12:58:00-04:00
**Constraint:** RST-C4
**Decision:** The disposition-history walk now asserts it actually read a
disposition map before diffing, and the rolled-back-action test now asserts the
write window closed again afterwards.
**Rationale:** Both were vacuous in the same way and neither showed it. If
`_dispositions_at` returned nothing — a parsing change, a path change — every
diff would be empty and the walk would pass having inspected no data. And a
failed action that left its write context open would leave the gate standing
open for every later caller, which is the worst version of that failure and the
one a rollback can quietly miss. Both were mutated: blinding the walk goes red,
and moving the context row outside the transaction goes red.

## DR-023 — A forbidden effect must be reachable, not merely false at baseline
**Time:** 2026-09-17T13:22:00-04:00
**Constraint:** RST-C4
**Decision:** A test removes the whole gate — every precondition and the
argument schema — reruns the gated set, and asserts every case lands. A case
that still reports `caught` against no gate at all is a case that measures
nothing.
**Rationale:** DR-012 asserts an effect is false before the case runs. That is a
different claim from the effect being *achievable*, and AC-302 sat in the
difference: it asserted `decided_by_id` could become `"noor"`, which no code
path in this system can produce under any mutation, because attribution is
derived inside the apply function and `update` refuses undeclared properties. It
counted toward `gated: 20` and `caught: 20` and was asserted over by the
compromised-agent invariant, while being incapable of failing. It was the only
gated case that did not flip when the gate was removed. The case is retargeted
at the approval itself, and the set-level mutation is now a standing test.

## DR-024 — The disclosure adjudicator matches raw text, never a serialization
**Time:** 2026-09-17T13:28:00-04:00
**Constraint:** RST-C5
**Decision:** `evaluate_effect` walks the raw strings of the transcript instead
of searching a `json.dumps` of it.
**Rationale:** `json.dumps` escapes quotes, backslashes and, by default, every
non-ASCII character. A marker containing any of those is absent from the
serialization while sitting verbatim in the agent's context, so the check
reports `caught` on a leak that happened — and it is the only adjudicator the
read-path class has. The current marker happens to be plain ASCII, which is
exactly why this survived: the check was correct for the one input it had.

## DR-025 — A rule that reads an argument declares which argument
**Time:** 2026-09-17T13:34:00-04:00
**Constraint:** RST-C2
**Decision:** `Precondition` carries `reads_args` alongside `reads`, and a test
asserts every action declares the parameters its rules read.
**Rationale:** `reads` is validated against the ontology, which cannot see
arguments, so three rules were reading `Facts.args` with nothing tying them to
the action's parameter list. Because evaluation is exhaustive, one predicate
raising kills the entire rejection rather than its own rule: attaching
`REASON_PRESENT` to `approve_request` would have been a live `KeyError` at the
write boundary with no forensic row. Only the ordering of the argument phase
before the rule phase was preventing it, and an ordering is not a declaration.

## DR-026 — A crashed action is recorded, not weakened into a footnote
**Time:** 2026-09-17T13:52:00-04:00
**Constraint:** RST-C1
**Decision:** An action that raises rolls back — mutation and forensic row
together — and then appends an `ERRORED` row outside the failed transaction.
The recording is itself guarded so a broken ledger cannot mask the failure it
is trying to record.
**Rationale:** Atomicity between the write and its row opens exactly one gap: a
crash leaves no trace that the action was ever attempted. The first response was
to narrow the module's claim from "every attempt" to "every verdict", which is
honest and is the wrong repair — the claim was worth keeping. Appending the
ERRORED row outside the rolled-back transaction keeps both properties: an
applied write still commits with its row or not at all, and a crash is a record
rather than a silence. Removing the ERRORED append goes red.

## DR-027 — Reachability is a numbered constraint, not a standing test
**Time:** 2026-09-17T14:20:00-04:00
**Constraint:** RST-C9
**Decision:** RST-C9: with the gate removed entirely — every precondition and
the argument schema — every gated case must flip to `missed`. It runs in the
standard suite. A case is admitted only when its forbidden effect is
demonstrably reachable, and a test asserts that reverting AC-302 to its original
effect makes the check red.
**Rationale:** It arrived as one more test among many, which understates what it
does. It is the check every other number in the register depends on: `caught: 20`
means twenty cases were refused only if all twenty could have landed, and
otherwise it is twenty minus however many could never have failed. Nothing else
in the suite can tell those two apart — AC-302 passed every other check, and a
review, while being incapable of failing. DR-012's "false in the seeded world"
is the weaker claim and is now explicitly named as insufficient at the point
where it is made.

The file also guards its own mechanism: if `_remove_the_gate` stopped removing
the gate, every case would still be refused and the whole constraint would pass
by refusing everything. That is asserted separately.

## DR-028 — Which finding leads the register is declared in the data
**Time:** 2026-09-17T14:46:00-04:00
**Constraint:** RST-C5
**Decision:** A case may carry `register_lead`. At most one may, it must be a
miss, and the register renders it first in the Missed section under an explicit
pointer. The README's miss table is asserted to lead with the same case.
**Rationale:** The misses were rendered in identifier order, which put the most
important finding in this repository third. A register that publishes its
strongest blind spot and buries it in an alphabetical list has done both things
at once. Making it a declared field rather than a sort heuristic keeps the
choice legible and reviewable — the author decides which finding a reader meets
first, and the decision is in the data where it can be argued with. The
alternative, ranking by how many actions landed, would have put AC-603 first by
coincidence this time and silently reordered the register the next time a case
was added.
