"""RST-C16: The constraint count is derived, not typed.

The README stated twelve constraints and named a test-file range. Nothing was
wrong when it was written and nothing went red when it stopped being true, which
is the same failure as a typed number inside a generated document.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from publish.readme import (
    constraint_numbers,
    constraint_test_files,
    stated_constraint_count,
)

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"


@pytest.fixture(scope="module")
def readme_text() -> str:
    return (ROOT / "README.md").read_text(encoding="utf-8")


def test_the_stated_count_equals_the_number_of_constraint_test_files(readme_text):
    stated = stated_constraint_count(readme_text)
    discovered = constraint_test_files(TESTS)
    assert stated is not None, "the README states no constraint count"
    assert stated == len(discovered), (
        f"the README says {stated}; {len(discovered)} constraint test files exist: "
        f"{[p.name for p in discovered]}"
    )


def test_the_discovery_actually_finds_files():
    """A count of nothing equals a README that says nothing."""
    assert len(constraint_test_files(TESTS)) >= 12


def test_the_constraints_are_numbered_without_a_gap():
    numbers = constraint_numbers(TESTS)
    assert numbers == list(range(1, len(numbers) + 1)), numbers


def test_the_readme_names_no_test_file_range(readme_text):
    """A named endpoint falls out of date on the commit that passes it."""
    assert "test_rst_c12_repeatable_verification.py" not in readme_text
    assert "through `tests/test_rst_c" not in readme_text


# --- the check fails when the tree and the README disagree ------------------


def _stub_tests(tmp_path: Path, count: int) -> Path:
    directory = tmp_path / "tests"
    directory.mkdir(exist_ok=True)
    for n in range(1, count + 1):
        (directory / f"test_rst_c{n}_thing.py").write_text("", encoding="utf-8")
    return directory


def test_it_fails_when_a_constraint_is_added_without_the_readme_following(tmp_path, readme_text):
    stated = stated_constraint_count(readme_text)
    widened = _stub_tests(tmp_path, stated + 1)
    assert len(constraint_test_files(widened)) != stated


def test_it_fails_when_a_constraint_is_removed(tmp_path, readme_text):
    stated = stated_constraint_count(readme_text)
    narrowed = _stub_tests(tmp_path, stated - 1)
    assert len(constraint_test_files(narrowed)) != stated


def test_the_control_passes(tmp_path, readme_text):
    stated = stated_constraint_count(readme_text)
    matching = _stub_tests(tmp_path, stated)
    assert len(constraint_test_files(matching)) == stated


def test_discovery_ignores_files_that_are_not_constraint_tests(tmp_path):
    directory = _stub_tests(tmp_path, 3)
    (directory / "conftest.py").write_text("", encoding="utf-8")
    (directory / "fake_surface.py").write_text("", encoding="utf-8")
    (directory / "test_rst_helper.py").write_text("", encoding="utf-8")
    assert len(constraint_test_files(directory)) == 3
