# Build log

Ordered decision records, oldest first. Each record states what was decided and
why. The log is published because the sequence is part of what this repository
demonstrates: nothing here was arrived at by accident, and the order in which
the pieces arrived is legible.

Format is fixed so it can be checked rather than trusted:
`tests/test_rst_c8_build_log.py` asserts that every record carries a timestamp,
a constraint, a decision and a rationale, and that the records are ordered.

---

## DR-001: The domain is an approval workflow with six actions
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

## DR-002: Persistence is SQLite from the standard library
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

## DR-003: The write boundary is three layers, and each is tested by attempting the bypass
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
forbidden operation. A check that passes because nobody currently attempts the
thing it forbids has not been shown to detect anything.

## DR-004: Fixtures load before the gate exists, not through a hole in it
**Time:** 2026-09-17T10:02:00-04:00
**Constraint:** RST-C1
**Decision:** `Store.create` returns an ungated database. Fixtures seed it.
`install_gate` then creates the triggers, and `bootstrap_insert` refuses from
that point on.
**Rationale:** The world contains requests already in terminal states and
principals with thresholds already set, a world no sequence of actions could
produce. The alternatives were a seeding bypass in the action layer, which is
exactly the escape hatch this repository exists to argue against, or fixtures
that cannot express a terminal state, which would delete a whole adversarial
class. Sequencing the gate after the seed costs nothing and leaves no hatch.

## DR-005: Preconditions are data, and declare which properties they read
**Time:** 2026-09-17T10:08:00-04:00
**Constraint:** RST-C2
**Decision:** Each precondition is a code, a sentence, a tuple of dotted
ontology property references, and a pure predicate. The references are resolved
against the ontology at import time.
**Rationale:** Declared reads make two things checkable that are otherwise
matters of intent: that no rule depends on a model-derived property, and that no
rule reads a property that does not exist. A typo in a rule is then a test
failure rather than a rule that silently never fires.

## DR-006: Preconditions are evaluated exhaustively, never short-circuited
**Time:** 2026-09-17T10:11:00-04:00
**Constraint:** RST-C2
**Decision:** A rejection names every rule that failed, not the first.
**Rationale:** An adversarial case declares which rejection it expects. If the
boundary short-circuits, that expectation becomes an assertion about evaluation
ORDER, and reordering the rules silently rewrites the expected results of the
case set. Collecting all failures makes the declared expectation stable.

## DR-007: `synchronous = OFF` on the store connection
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

## DR-008: Rule coverage is asserted, not reviewed
**Time:** 2026-09-17T10:32:00-04:00
**Constraint:** RST-C2
**Decision:** A test derives the set of (action, precondition) pairs from the
registry and asserts that the violation table exercises every one of them.
**Rationale:** The failure mode for a rule table is not a wrong rule, it is a
rule nobody tests, which then stops holding without anything going red. Deriving
the expected set from the registry means adding a precondition without a
violating case is a test failure on the commit that adds it.

## DR-009: Identifier matches in source scans are whole-token, never substring
**Time:** 2026-09-17T10:38:00-04:00
**Constraint:** RST-C2
**Decision:** The scan asserting that no module re-implements a rejection code
matches on word boundaries.
**Rationale:** The substring form reported `gate/ontology.py` for the rejection
code `TERMINAL_STATE`, because the ontology declares `TERMINAL_STATES`. A check
with a false positive is worse than no check: the next person to hit it turns it
off, and then the true positives go with it.

## DR-010: The adversarial set is data; the class list is code
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

## DR-011: `gated` partitions the set, and reconciles RST-C3 with RST-C5
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
none of those land. The misses are writes no rule covers, which is a statement
about the ontology, not about the enforcement. Making the partition a required
field means the distinction is in the data rather than in a paragraph someone
has to remember.

## DR-012: A forbidden effect must be false before the case runs
**Time:** 2026-09-17T11:04:00-04:00
**Constraint:** RST-C4
**Decision:** A test evaluates every case's `forbidden_effect` against a freshly
seeded world with no steps executed, and fails if any is already true.
**Rationale:** Found by building it wrong. AC-602's forbidden effect matched any
$48,000 request in SUBMITTED, and the seeded world contains one, so the case
reported `missed` regardless of what the gate did. The failure is silent in the
worst direction: it manufactures a fake blind spot, and a register entry that is
not real is worse than a missing one, because it is published.

## DR-013: Every case runs against its own freshly seeded database
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

## DR-014: The hostile driver has no refusal path
**Time:** 2026-09-17T11:18:00-04:00
**Constraint:** RST-C3
**Decision:** The driver is deterministic, executes every step, and executes
every instruction it finds in tool output. There is no branch in it that
declines.
**Rationale:** A model adversary would decline sometimes, and then a green run
is evidence about the model's disposition rather than about the gate. Maximal
credulity makes the driver a stronger adversary than the thing it replaces, and
it makes every result in this repository reproducible by anyone with a clone and
no credential. The cost is that the injection format is synthetic, a marker and
a JSON payload, which is stated in the module rather than hidden.

## DR-015: The register embeds its own counts, machine-readable
**Time:** 2026-09-17T11:34:00-04:00
**Constraint:** RST-C5
**Decision:** `RunResult.counts()` computes every published number exactly once.
The register renders them into prose and into a fenced JSON block, and a test
parses the block and compares it to the run.
**Rationale:** RST-C5 requires that every count in the document match the count
computed from the run. Asserting that against prose means parsing English. A
machine-readable block makes the assertion exact, and rendering both from one
dictionary means the prose and the block cannot drift: there is no second place
where a number is decided. The counts are also mutated: dropping a case from the
run must move them, which is what distinguishes a derived number from a typed
one.

## DR-016: The README artifact carries no volatile field at all
**Time:** 2026-09-17T11:40:00-04:00
**Constraint:** RST-C6
**Decision:** The SVG contains no timestamp, no duration, no path and no port.
Regeneration is asserted by byte equality, and a second test asserts the
volatile normaliser changes nothing in it.
**Rationale:** The allowlist permits volatile fields; producing none is
strictly stronger, and it removes the way this assertion usually rots, which is
an equivalence check whose normaliser quietly grows until it is comparing almost
nothing. The paired test is the guard: byte equality is only meaningful once you
have shown that nothing volatile was excluded from the comparison.

## DR-017: The artifact selects its case from the data
**Time:** 2026-09-17T11:44:00-04:00
**Constraint:** RST-C6
**Decision:** The renderer takes the first gated case of a named class rather
than a named case identifier. Every value on the panel (amount, threshold,
rejection code, message, state afterwards) is read out of the run it performs.
**Rationale:** The test forbidding any module from hardcoding a case identifier
caught the first version, which named `AC-101`. The exemption was available and
would have been reasonable-sounding. Selecting from the data instead makes the
picture a view onto the case set rather than a second story about it, and means
the panel cannot show something the suite is not also asserting.

## DR-018: The default path has no provider, and nothing is structured to need one
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
live mode possible without inviting it into the gating set. A model-driven run
would be a development aid, and a development aid does not get to decide whether
the suite is green.

## DR-019: The build log has a fixed format so it can be checked
**Time:** 2026-09-17T12:06:00-04:00
**Constraint:** RST-C8
**Decision:** Each record is `## DR-NNN: title` followed by `**Time:**`,
`**Constraint:**`, `**Decision:**` and `**Rationale:**`. A test parses them and
asserts the numbering has no gap, the timestamps are real and in order, every
record names a constraint, and every constraint has at least one record.
**Rationale:** A build log published as evidence is a deliverable, and a
deliverable gets a gate like everything else here. The specific thing worth
catching is a record with a decision and no reason, which is the shape a log
degrades into: still ordered, still timestamped, no longer explaining anything.

## DR-020: Pace is inferred from the log; the README claims nothing about it
**Time:** 2026-09-17T12:10:00-04:00
**Constraint:** RST-C8
**Decision:** No elapsed-time claim appears in the README, and a test asserts it
against ten phrasings, paired with a test that the same check does not fire on
ordinary prose.
**Rationale:** Every claim in this repository names the gate that proves it, and
no gate can prove elapsed time. A decision log with ordered timestamps is
evidence and needs no claim attached; a reader who cares can read the sequence
and draw their own conclusion, which is worth more than a sentence asserting it.
The false-positive half of the test is not decoration: a check that flags
"a five-state machine" would be disabled by the next person to hit it, and the
true positives would go with it.

## DR-021: Three gaps closed by reading the write interface back
**Time:** 2026-09-17T12:38:00-04:00
**Constraint:** RST-C1
**Decision:** An action context refuses to update an object's key; the forensic
record for an applied action commits inside the same transaction as the
mutation; and the case loader validates the shape of every `forbidden_effect`.
**Rationale:** None of the three was reachable from the adversarial set, which
is exactly why they are worth naming. An identity update is a substitution that
silently detaches every link pointing at the old key. A forensic record written
after the commit means a landed write with no row in the ledger is a state the
system can reach, in an append-only log whose whole purpose is that it cannot.
A malformed effect surfaces as a `KeyError` mid-run, by which time the case has
already been reported as something. Each guard was verified by removing it and
watching the test go red.

## DR-022: Two assertions that could have passed having checked nothing
**Time:** 2026-09-17T12:58:00-04:00
**Constraint:** RST-C4
**Decision:** The disposition-history walk now asserts it actually read a
disposition map before diffing, and the rolled-back-action test now asserts the
write window closed again afterwards.
**Rationale:** Both were vacuous in the same way and neither showed it. If
`_dispositions_at` returned nothing (a parsing change, a path change), every
diff would be empty and the walk would pass having inspected no data. And a
failed action that left its write context open would leave the gate standing
open for every later caller, which is the worst version of that failure and the
one a rollback can quietly miss. Both were mutated: blinding the walk goes red,
and moving the context row outside the transaction goes red.

## DR-023: A forbidden effect must be reachable, not merely false at baseline
**Time:** 2026-09-17T13:22:00-04:00
**Constraint:** RST-C4
**Decision:** A test removes the whole gate, both every precondition and the
argument schema, reruns the gated set, and asserts every case lands. A case
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

## DR-024: The disclosure adjudicator matches raw text, never a serialization
**Time:** 2026-09-17T13:28:00-04:00
**Constraint:** RST-C5
**Decision:** `evaluate_effect` walks the raw strings of the transcript instead
of searching a `json.dumps` of it.
**Rationale:** `json.dumps` escapes quotes, backslashes and, by default, every
non-ASCII character. A marker containing any of those is absent from the
serialization while sitting verbatim in the agent's context, so the check
reports `caught` on a leak that happened, and it is the only adjudicator the
read-path class has. The current marker happens to be plain ASCII, which is
exactly why this survived: the check was correct for the one input it had.

## DR-025: A rule that reads an argument declares which argument
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

## DR-026: A crashed action is recorded, not weakened into a footnote
**Time:** 2026-09-17T13:52:00-04:00
**Constraint:** RST-C1
**Decision:** An action that raises rolls back, mutation and forensic row
together, and then appends an `ERRORED` row outside the failed transaction.
The recording is itself guarded so a broken ledger cannot mask the failure it
is trying to record.
**Rationale:** Atomicity between the write and its row opens exactly one gap: a
crash leaves no trace that the action was ever attempted. The first response was
to narrow the module's claim from "every attempt" to "every verdict", which is
honest and is the wrong repair: the claim was worth keeping. Appending the
ERRORED row outside the rolled-back transaction keeps both properties: an
applied write still commits with its row or not at all, and a crash is a record
rather than a silence. Removing the ERRORED append goes red.

## DR-027: Reachability is a numbered constraint, not a standing test
**Time:** 2026-09-17T14:20:00-04:00
**Constraint:** RST-C9
**Decision:** RST-C9: with the gate removed entirely, both every precondition
and the argument schema, every gated case must flip to `missed`. It runs in the
standard suite. A case is admitted only when its forbidden effect is
demonstrably reachable, and a test asserts that reverting AC-302 to its original
effect makes the check red.
**Rationale:** It arrived as one more test among many, which understates what it
does. It is the check every other number in the register depends on: `caught: 20`
means twenty cases were refused only if all twenty could have landed, and
otherwise it is twenty minus however many could never have failed. Nothing else
in the suite can tell those two apart. AC-302 passed every other check, and a
review, while being incapable of failing. DR-012's "false in the seeded world"
is the weaker claim and is now explicitly named as insufficient at the point
where it is made.

The file also guards its own mechanism: if `_remove_the_gate` stopped removing
the gate, every case would still be refused and the whole constraint would pass
by refusing everything. That is asserted separately.

## DR-028: Which finding leads the register is declared in the data
**Time:** 2026-09-17T14:46:00-04:00
**Constraint:** RST-C5
**Decision:** A case may carry `register_lead`. At most one may, it must be a
miss, and the register renders it first in the Missed section under an explicit
pointer. The README's miss table is asserted to lead with the same case.
**Rationale:** The misses were rendered in identifier order, which put the most
important finding in this repository third. A register that publishes its
strongest blind spot and buries it in an alphabetical list has done both things
at once. Making it a declared field rather than a sort heuristic keeps the
choice legible and reviewable: the author decides which finding a reader meets
first, and the decision is in the data where it can be argued with. The
alternative, ranking by how many actions landed, would have put AC-603 first by
coincidence this time and silently reordered the register the next time a case
was added.

## DR-029: The transport is injected so the failure modes are testable offline
**Time:** 2026-09-17T15:12:00-04:00
**Constraint:** RST-C10
**Decision:** Every check takes a fetcher. The suite injects canned responses;
`make verify-public` injects `UrllibFetcher`. Each check is exercised twice,
against a correct surface and a deliberately broken one.
**Rationale:** "Point it at something broken and require it to notice" must not
mean breaking the published repository to find out. Separating the fetching from
the deciding makes a missing artifact, a stale asset that still answers 200, an
image rendered below the first heading, a 404 link and an unreachable host all
ordinary unit tests. It also keeps the suite hermetic: `make test` does not
depend on a network for its verdicts.

## DR-030: Three outcomes, because unknown is not a pass
**Time:** 2026-09-17T15:18:00-04:00
**Constraint:** RST-C11
**Decision:** `PASS`, `FAIL` and `UNAVAILABLE`. The first two are claims about
the repository; the third is a claim about the evidence. All of `UNAVAILABLE`
exits non-zero and is reported in its own sentence.
**Rationale:** The failure this is written against is an unreachable API reading
as a successful publication. A 403 rate-limit says nothing about visibility, and
reporting it as "not public" invents a finding out of missing evidence, which is
the mirror of the same error. A 404 to an anonymous query IS a finding, because
that is exactly what a private repository looks like to a visitor. The
distinction is asserted: a broken surface and an unreachable one produce
different statuses and different text.

## DR-031: The slug is derived from the git remote
**Time:** 2026-09-17T15:24:00-04:00
**Constraint:** RST-C12
**Decision:** `repo_slug` parses `git remote get-url origin`; the branch comes
from `rev-parse --abbrev-ref HEAD`. The entry point takes no arguments.
**Rationale:** A constant naming the owner and repository would be a second copy
of a fact that already exists, and second copies drift. This one would drift
silently, because a checker pointed at the wrong repository still reports five
green checks. Deriving it also makes the command re-runnable from a fork or a
rename without editing anything.

## DR-032: The surface checker lives outside the gate package
**Time:** 2026-09-17T15:30:00-04:00
**Constraint:** RST-C12
**Decision:** `publish/`, not `gate/`. A test asserts no module in `gate/`
imports it.
**Rationale:** RST-C7 asserts that nothing on the default path imports a network
library, and `make demo` opening a socket would make the published register
depend on the weather. The checker opens sockets by definition. Putting it in
`gate/` would have forced a weakening of the RST-C7 scan, which is the shape of
every bypass this repository argues against, arriving as a reasonable
convenience.

## DR-033: The rendered image source is fetched, not assumed
**Time:** 2026-09-17T15:52:00-04:00
**Constraint:** RST-C10
**Decision:** `check_above_fold` extracts the `src` from the first `<img>`
above the first heading, resolves it (relative, root-relative or absolute),
fetches it, and requires a 200 with an `image/*` content type.
**Rationale:** The check previously asserted that an `<img>` tag existed above
the first heading, and a separate check asserted the raw asset was reachable.
Neither asserted that the src THE RENDERED VIEW CARRIES resolves to it. A
visitor sees a broken image in exactly that case and both checks stay green,
which on a flagship above-fold artifact is the most expensive failure available
and was the one the constraint was written to prevent. The three src forms
resolve against three different bases, and guessing one would make the check
pass by accident on the other two.

## DR-034: A typographic pass was applied across the build log and the lessons
**Time:** 2026-09-17T16:40:00-04:00
**Constraint:** RST-C14
**Decision:** A typographic pass removed every em-dash class character from the
tracked tree by recasting the sentence each one appeared in, and RST-C13 now gates the class across
every tracked and untracked-but-not-ignored text file. `DECISIONS.md` and
`LESSONS.md` were edited in bulk as part of that pass.
**Rationale:** The character is a recognised marker of machine-generated prose.
This repository's author discloses AI collaboration directly; a reader inferring
it from typography before reaching that disclosure is a different thing, and it
is not wanted. Correcting only the rendered files would have left the renderers
and the case data untouched, so the next `make demo` would have put every
occurrence back.

**Files and counts.** 142 occurrences of U+2014, plus two more in `gate/cast.py`
written as `backslash-u` escape sequences that decoded to the character at
render time:

| File | Occurrences | |
|---|---:|---|
| `DECISIONS.md` | 64 | source |
| `LESSONS.md` | 36 | source |
| `README.md` | 11 | source |
| `docs/KNOWN-MISSES.md` | 8 | generated |
| `gate/register.py` | 6 | source |
| `publish/__main__.py` | 4 | source |
| `assets/blocked-write.svg` | 3 | generated |
| `tests/test_rst_c8_build_log.py` | 3 | source |
| `cases/adversarial/03-identity-confusion.json` | 2 | source |
| `gate/__main__.py` | 2 | source |
| `cases/adversarial/01-injection-via-tool-output.json` | 1 | source |
| `cases/adversarial/05-argument-coercion.json` | 1 | source |
| `gate/cast.py` | 1 character, 2 escapes | source |

131 were in source and 11 in generated output. A further 49 ASCII double hyphens
used as dashes were recast in the same pass across 24 files, 13 of them module
docstring headings, because a double hyphen substituted for an em dash is its
own marker and leaving them would have removed one tell and kept an identical
one.

**Substance.** No decision, rationale, lesson, count, case commentary, rejection
code or claim was altered. Every change is punctuation and the sentence
structure around it: a comma, a semicolon, a colon, parentheses, or two
sentences, chosen for the sentence it appeared in rather than applied as a
substitution. Two structural consequences are worth naming because they are not
punctuation. The record headings changed from `## DR-NNN <dash> title` to
`## DR-NNN: title`, and `tests/test_rst_c8_build_log.py` follows with the same
separator; the assertions it makes are unchanged in strength, still requiring
every record to be numbered, ordered, titled, timestamped and constraint-bearing.
The register's entry headings changed the same way, and the artifact's panel now
reads `state = SUBMITTED (unchanged)` where it read `state = SUBMITTED <dash>
unchanged`.

**History.** Git history is not rewritten. Every commit before this one still
contains the original characters in its file versions and in its commit
messages, and that is deliberate. The commit SHAs are referenced by review
artifacts on disk, and the ordered commit timestamps are the evidence RST-C8 and
D-6 rest on: the build log is published because the sequence is part of what
this repository demonstrates, and rewriting it to look as though the prose had
always been this way would destroy the one property a build log cannot afford to
lose. A log that has been edited in bulk and does not say so reads as though it
was always written that way. This record is the alternative.

## DR-035: The dash check matches a class and reads the source, not the output
**Time:** 2026-09-17T16:52:00-04:00
**Constraint:** RST-C13
**Decision:** The class is built from the Unicode Dash_Punctuation category with
a documented exclusion list, plus four lookalikes Unicode does not file as
dashes. The scan covers tracked and untracked-but-not-ignored text files, and it
decodes escape sequences as well as reading characters.
**Rationale:** Three ways this check goes green while the defect is present, and
each is closed rather than hoped about. A check for U+2014 alone stays green
against a visually identical substitute, so the class is enumerated rather than
a codepoint. A check over committed output stays green while the renderer that
wrote it still emits the character, so the source is scanned and the generated
files are regenerated and rescanned. And a check over `git ls-files` cannot see
a file that is not yet tracked, so a new file carrying the character would pass
until the commit that adds it, which is one commit too late.

The escape clause is the one found by execution rather than by reasoning:
`gate/cast.py` carried two backslash-u escapes that were invisible to a scan of
the tree and plain in the SVG the module wrote.

## DR-036: The README carries a route to the register's lead finding
**Time:** 2026-09-17T16:58:00-04:00
**Constraint:** RST-C15
**Decision:** One sentence immediately after the statistics line names the case
carrying `register_lead` and links to the register. A test reads the identifier
from the case data and asserts the README matches it.
**Rationale:** The register already led with AC-603 and the README already
stated `4 missed`, and a reader going top to bottom met neither. The only route
from the README to the register was a row in the repository map table, which is
a reference list rather than a destination. The sentence states what the case is
rather than that it is worth reading, because a reader who is told a finding is
interesting has been given an opinion and a reader who is told an approver
cleared $48,000 against a $10,000 threshold has been given the finding.

## DR-037: The constraint count is discovered from the test files
**Time:** 2026-09-17T17:04:00-04:00
**Constraint:** RST-C16
**Decision:** The README states the count in a fixed form and a test compares it
to the number of `tests/test_rst_c<n>_*.py` files present. The named test-file
range is removed rather than derived.
**Rationale:** The README said twelve constraints and named the range from
`test_rst_c1_write_boundary.py` to `test_rst_c12_repeatable_verification.py`.
Nothing was wrong when that was written and nothing went red when it stopped
being true, which is the same failure as a typed number inside a generated
document. A range is worse than a count because both endpoints rot and the lower
one looks permanent. The count stays in prose because a README cannot compute,
but it is now compared against the tree on every run.

## DR-038: Constraint identifiers are matched on a boundary, not as substrings
**Time:** 2026-09-17T17:30:00-04:00
**Constraint:** RST-C8
**Decision:** `names_constraint` matches an identifier followed by anything that
is not a digit, and the commit-coverage check in `tests/test_rst_c8_build_log.py`
uses it. The RST-C14 record lookup uses it too.
**Rationale:** Arrived by hand from a parallel lane as a class to probe, and it
was present. The check read `any(rst in c for c in commits)`, and `RST-C1` is a
substring of `RST-C16`, so a commit naming only RST-C16 reported RST-C1 as
covered. That is wrong now rather than prospectively: this repository has
sixteen constraints, and the front-page work is what took it past nine.

The boundary is a negative lookahead on a digit rather than `\b`, because `\b`
sits happily between `RST-C1` and the `6` that follows it. Measured on a commit
reading `RST-C16: front page`: the substring form reports RST-C1 covered, the
boundary form does not, and the control, a commit genuinely naming RST-C1, still
matches.

## DR-039: An unreadable file fails the scan instead of shrinking it
**Time:** 2026-09-17T17:44:00-04:00
**Constraint:** RST-C13
**Decision:** `text_population` raises `UnreadableFile` on anything that stops a
read, counts undecodable content as a deliberate binary skip, and asserts that
the files read plus the files skipped equal the files listed. `scan_repository`
goes through it.
**Rationale:** Arrived by hand from a parallel lane as a class to probe, and it
was present in the code written for RST-C13 two commits earlier. The scan caught
`UnicodeDecodeError` and `OSError` together and continued, so a file that could
not be opened was indistinguishable from a file with nothing in it. A file
denied by permissions would have been dropped and the scan would have reported
green over it.

The two cases are not the same and are now separated. Undecodable content is a
binary file, there is no prose in it, and it is skipped and counted. Anything
else is an error. The denominator is asserted rather than implied, because a
population that shrinks quietly turns a smaller pass into an indistinguishable
one.

Measured in a temporary repository: two files, one carrying a planted dash.
Readable, the scan returns one hit. With that file at mode 000 the scan raises
and names it; under the previous code it returned no hits and passed.

## DR-040: The publish entry point parses its arguments
**Time:** 2026-09-17T17:56:00-04:00
**Constraint:** RST-C12
**Decision:** `python -m publish` parses `argv` with `argparse` and refuses
anything it does not declare, which is everything: the command takes no
arguments. `--help` still exits 0 without running the checks.
**Rationale:** Arrived by hand from a parallel lane as a class to probe, and it
was present here. `main` accepted `argv` and never looked at it, so `--checkk`,
`-c` and `--help` all fell through to the default path and exited 0. The
default path here only reads, so the cost was a wrong green rather than a wrong
write. That is the accident of this command rather than a property of the
shape, and the shape is what was wrong.

The regeneration entry point was probed in the same sweep and was already
sound: `python -m gate` has used `argparse` since it was written, and a
near-miss flag exits non-zero. That is now asserted by execution rather than by
reading, with a control that the right arguments do write.
