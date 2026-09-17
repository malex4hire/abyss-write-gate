"""RST-C5: The known-miss register is non-empty and generated.

The register is the highest-value artifact here, so the assertions on it are
the strictest: it must regenerate byte-identically apart from the one
allowlisted volatile field, every number in it must be derived from the run,
and the missed set must not be empty.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

import pytest

from gate import register
from gate.cases import MISS_REASON_CLASSES
from gate.register import normalize_volatile, parse_counts, render

ROOT = Path(__file__).resolve().parent.parent
COMMITTED = ROOT / register.REGISTER_PATH


@pytest.fixture(scope="module")
def committed() -> str:
    assert COMMITTED.exists(), "the register is not committed"
    return COMMITTED.read_text(encoding="utf-8")


# --- generated, not maintained ---------------------------------------------


def test_regeneration_reproduces_the_committed_register(committed, hostile_run):
    """Modulo the volatile-field allowlist, and nothing else."""
    regenerated = render(hostile_run)
    assert normalize_volatile(regenerated) == normalize_volatile(committed)


def test_the_only_volatile_field_in_the_register_is_the_timestamp(committed, hostile_run):
    """Name what the allowlist is actually covering here, rather than waving at it."""
    regenerated = render(hostile_run)
    differing = [
        (a, b)
        for a, b in zip(regenerated.splitlines(), committed.splitlines())
        if a != b
    ]
    assert len(differing) <= 1
    for a, b in differing:
        assert a.startswith(register.TIMESTAMP_LINE)
        assert b.startswith(register.TIMESTAMP_LINE)


def test_the_normaliser_blanks_a_timestamp_and_nothing_else():
    """Mutate the check: a normaliser that blanks everything would pass above."""
    a = "**Generated:** 2026-09-17T14:19:57+00:00 and 20 caught"
    b = "**Generated:** 2030-01-02T03:04:05+00:00 and 20 caught"
    c = "**Generated:** 2030-01-02T03:04:05+00:00 and 19 caught"
    assert normalize_volatile(a) == normalize_volatile(b)
    assert normalize_volatile(a) != normalize_volatile(c)


# --- every count matches the run -------------------------------------------


def test_every_count_in_the_register_matches_the_run(committed, hostile_run):
    assert parse_counts(committed) == hostile_run.counts()


def test_the_counts_are_derived_rather_than_typed(hostile_run):
    """Drop a case and require every affected number to move."""
    reduced = dataclasses.replace(hostile_run, runs=hostile_run.runs[:-1])
    original = parse_counts(render(hostile_run))
    mutated = parse_counts(render(reduced))
    assert mutated["cases"] == original["cases"] - 1
    assert mutated != original


def test_the_summary_table_and_the_machine_block_cannot_disagree(committed):
    counts = parse_counts(committed)
    assert f"| Cases | {counts['cases']} |" in committed
    assert f"| Caught | {counts['caught']} |" in committed
    assert f"| **Missed** | **{counts['missed']}** |" in committed
    assert (
        f"| **Forbidden mutations that landed** | "
        f"**{counts['forbidden_mutations_landed']}** |" in committed
    )


# --- the missed set ---------------------------------------------------------


def missed_set_defects(result) -> list[str]:
    """Everything that would make the register dishonest. Mutated below."""
    problems: list[str] = []
    if not result.missed:
        problems.append("the missed set is empty: the adversarial set is too weak")
    for run in result.missed:
        if not run.case.miss_reason_class:
            problems.append(f"{run.case.id}: missed with no reason class")
        elif run.case.miss_reason_class not in MISS_REASON_CLASSES:
            problems.append(f"{run.case.id}: undeclared reason class")
    return problems


def test_the_missed_set_is_non_empty_and_every_miss_carries_a_reason_class(hostile_run):
    assert missed_set_defects(hostile_run) == []
    assert len(hostile_run.missed) >= 1


def test_an_empty_missed_set_is_reported_as_a_defect(hostile_run):
    """Mutate the check. An empty register must fail, not pass quietly."""
    all_caught = dataclasses.replace(hostile_run, runs=hostile_run.caught)
    problems = missed_set_defects(all_caught)
    assert problems == ["the missed set is empty: the adversarial set is too weak"]


def test_a_miss_without_a_reason_class_is_reported_as_a_defect(hostile_run):
    stripped = dataclasses.replace(
        hostile_run,
        runs=[
            dataclasses.replace(r, case=dataclasses.replace(r.case, miss_reason_class=None))
            if r.disposition == "missed"
            else r
            for r in hostile_run.runs
        ],
    )
    problems = missed_set_defects(stripped)
    assert len(problems) == len(hostile_run.missed)
    assert all("no reason class" in p for p in problems)


# --- every case is labelled -------------------------------------------------


def test_every_case_appears_in_the_register_labelled_caught_or_missed(
    committed, hostile_run
):
    missed_section = committed.split("## Missed", 1)[1].split("## Reason classes", 1)[0]
    caught_section = committed.split("## Caught", 1)[1]
    for run in hostile_run.runs:
        in_missed = run.case.id in missed_section
        in_caught = run.case.id in caught_section
        assert in_missed != in_caught, f"{run.case.id} is labelled {in_missed=} {in_caught=}"
        assert in_missed == (run.disposition == "missed")


def test_every_reason_class_in_the_register_carries_its_meaning(committed):
    for reason, meaning in MISS_REASON_CLASSES.items():
        if f"`{reason}`" in committed:
            assert meaning in committed


def test_the_register_names_the_command_that_regenerates_it(committed):
    assert "make demo" in committed


def test_the_register_contains_no_credential_shaped_string(committed):
    for pattern in (r"sk-[A-Za-z0-9]{8,}", r"AKIA[0-9A-Z]{16}", r"ghp_[A-Za-z0-9]{20,}"):
        assert not re.search(pattern, committed)


# --- the README quotes the same numbers -------------------------------------

README = ROOT / "README.md"
HEADLINE = re.compile(
    r"\*\*(\d+) cases · (\d+) classes · (\d+) caught · (\d+) missed "
    r"· (\d+) forbidden mutations landed\.\*\*"
)


def test_the_readme_headline_matches_the_run():
    """The one place a count is typed by hand, and it is asserted.

    A number in prose drifts the moment the set grows. This is the guard, and
    the format is fixed so the guard can parse it rather than guess.
    """
    match = HEADLINE.search(README.read_text(encoding="utf-8"))
    assert match, "the README headline counts are missing or reformatted"
    cases, classes, caught, missed, landed = (int(g) for g in match.groups())
    counts = parse_counts(COMMITTED.read_text(encoding="utf-8"))
    assert (cases, classes, caught, missed, landed) == (
        counts["cases"],
        counts["classes"],
        counts["caught"],
        counts["missed"],
        counts["forbidden_mutations_landed"],
    )


def test_the_readme_lists_every_miss_with_its_reason_class(hostile_run):
    readme = README.read_text(encoding="utf-8")
    for run in hostile_run.missed:
        assert run.case.id in readme, f"{run.case.id} is missing from the README"
        assert f"`{run.case.miss_reason_class}`" in readme


# --- the lead entry ---------------------------------------------------------


def test_exactly_one_case_leads_the_register_and_it_is_a_miss():
    """Which finding a reader sees first is a decision, so it is recorded as one."""
    from gate.cases import load_cases

    leads = [c for c in load_cases() if c.register_lead]
    assert len(leads) == 1, f"expected one lead, got {[c.id for c in leads]}"
    assert leads[0].expected_disposition == "missed"


def test_the_lead_entry_appears_first_in_the_missed_section(committed):
    from gate.cases import load_cases

    lead = next(c for c in load_cases() if c.register_lead)
    missed_section = committed.split("## Missed", 1)[1].split("## Reason classes", 1)[0]
    headings = re.findall(r"^### (AC-\d{3})", missed_section, re.M)
    assert headings[0] == lead.id, f"the register leads with {headings[0]}, not {lead.id}"
    assert f"**Read {lead.id} first" in missed_section


def test_the_readme_leads_its_miss_table_with_the_same_case():
    """A register that leads with one finding and a README that leads with
    another has published a priority and then contradicted it."""
    from gate.cases import load_cases

    lead = next(c for c in load_cases() if c.register_lead)
    readme = README.read_text(encoding="utf-8")
    section = readme.split("## What the gate misses", 1)[1].split("\n## ", 1)[0]
    rows = re.findall(r"^\| (AC-\d{3}) \|", section, re.M)
    assert rows, "the README miss table is missing or reformatted"
    assert rows[0] == lead.id, f"the README leads with {rows[0]}, not {lead.id}"
    assert set(rows) == {c.id for c in load_cases() if c.expected_disposition == "missed"}
    # and the prose above the table names it too
    assert lead.id in section.split("|", 1)[0], "the section text does not name the lead"
