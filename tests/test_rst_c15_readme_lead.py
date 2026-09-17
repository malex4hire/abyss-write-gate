"""RST-C15: The README points a reader at the declared lead finding.

The register leads with a case. The README is where a reader arrives, and until
now the only route to that case from the README was a row in the repository map
table, which a reader going top to bottom never treats as a destination.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gate.cases import load_cases
from publish.readme import above_the_fold, lead_reference

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"


@pytest.fixture(scope="module")
def readme_text() -> str:
    return README.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def declared_lead() -> str:
    leads = [c for c in load_cases() if c.register_lead]
    assert len(leads) == 1
    return leads[0].id


def test_the_readme_names_the_lead_case_above_the_fold(readme_text, declared_lead):
    named, linked = lead_reference(readme_text)
    assert named == declared_lead, f"the README leads with {named}, the data with {declared_lead}"
    assert linked, "the register is not linked above the fold"


def test_the_reference_sits_after_the_statistics_line(readme_text):
    fold = above_the_fold(readme_text)
    stats = fold.index("forbidden mutations landed")
    reference = fold.index("AC-")
    assert reference > stats, "the lead reference precedes the statistics line"


def test_the_reference_says_what_the_case_is(readme_text):
    """It states the case, not that the case is interesting."""
    fold = above_the_fold(readme_text)
    sentence = fold[fold.index("AC-"):]
    for token in ("$10,000", "$9,600", "$48,000", "ontology"):
        assert token in sentence, f"the reference does not state {token}"
    for empty in ("interesting", "worth reading", "fascinating", "the best"):
        assert empty not in sentence.lower()


def test_the_reference_is_brief(readme_text):
    fold = above_the_fold(readme_text)
    tail = fold[fold.index("The one to read first"):]
    assert tail.count(".") <= 3, "one or two sentences"


# --- the check fails when the two disagree ----------------------------------


def test_it_fails_when_the_readme_names_a_different_case(readme_text, declared_lead):
    other = "AC-701"
    assert other != declared_lead
    mutated = readme_text.replace(declared_lead, other, 1)
    named, _ = lead_reference(mutated)
    assert named == other
    assert named != declared_lead, "naming a different case must be visible"


def test_it_fails_when_the_lead_moves_and_the_readme_does_not_follow(readme_text):
    """`register_lead` moving is a data change. The README must follow it."""
    named, _ = lead_reference(readme_text)
    moved_lead = "AC-303"
    assert named != moved_lead, (
        "if the declared lead moved to AC-303 the README would still name "
        f"{named}, and this comparison is what notices"
    )


def test_it_fails_when_the_register_is_not_linked_above_the_fold(readme_text):
    unlinked = readme_text.replace("](docs/KNOWN-MISSES.md)", "](elsewhere.md)", 1)
    _, linked = lead_reference(unlinked)
    assert not linked


def test_the_control_passes_on_the_unmodified_readme(readme_text, declared_lead):
    named, linked = lead_reference(readme_text)
    assert (named, linked) == (declared_lead, True)
