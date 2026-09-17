"""What the README claims about the repository, and how to check it.

Two claims here are typed into a markdown file and cannot compute themselves:
the number of constraints, and which finding a reader should meet first. Both
are true today and neither goes red on its own when it stops being true, which
is the same shape as a typed count inside a generated document. So both are
derived from the tree and compared against what the README says.
"""

from __future__ import annotations

import re
from pathlib import Path

CONSTRAINT_TEST = re.compile(r"^test_rst_c(\d+)_.+\.py$")
STATED_COUNT = re.compile(r"\*\*(\d+) numbered constraints\*\*")
CASE_REFERENCE = re.compile(r"(AC-\d{3})")
REGISTER_LINK = re.compile(r"\]\(\s*docs/KNOWN-MISSES\.md\s*\)")


def constraint_test_files(tests_dir: Path) -> list[Path]:
    """One file per constraint, discovered rather than listed."""
    return sorted(
        path
        for path in Path(tests_dir).glob("test_rst_c*.py")
        if CONSTRAINT_TEST.match(path.name)
    )


def constraint_numbers(tests_dir: Path) -> list[int]:
    return sorted(
        int(CONSTRAINT_TEST.match(p.name).group(1))
        for p in constraint_test_files(tests_dir)
    )


def stated_constraint_count(readme_text: str) -> int | None:
    match = STATED_COUNT.search(readme_text)
    return int(match.group(1)) if match else None


def above_the_fold(readme_text: str) -> str:
    """Everything before the first section heading.

    The artifact, the title, the opening claim and the statistics line. What a
    reader meets before deciding whether to keep going.
    """
    match = re.search(r"^## ", readme_text, re.M)
    return readme_text[: match.start()] if match else readme_text


def lead_reference(readme_text: str) -> tuple[str | None, bool]:
    """The case identifier named above the fold, and whether the register is
    linked there."""
    fold = above_the_fold(readme_text)
    found = CASE_REFERENCE.search(fold)
    return (found.group(1) if found else None), bool(REGISTER_LINK.search(fold))


# A constraint identifier is a prefix of every longer one: `RST-C1` is a
# substring of `RST-C10`, `RST-C11` and `RST-C16`. A plain `in` test therefore
# reports RST-C1 as covered by a commit that names only RST-C16, which is wrong
# today rather than prospectively: this repository has sixteen constraints.
_TRAILING_DIGIT = "(?!\\d)"


def names_constraint(text: str, identifier: str) -> bool:
    """True when `text` names exactly this constraint.

    The boundary is a negative lookahead on a digit rather than `\\b`, because
    `\\b` sits happily between `RST-C1` and the `6` that follows it.
    """
    return re.search(re.escape(identifier) + _TRAILING_DIGIT, text) is not None
