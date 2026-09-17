"""RST-C14: The typographic pass records itself in the build log.

`DECISIONS.md` and `LESSONS.md` are forensic records, and a bulk edit across
them is a bulk operation on a forensic record. The punctuation is not the claim,
so the edit is permissible. A log that has been rewritten and does not say so is
not.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DECISIONS = ROOT / "DECISIONS.md"

RECORD = re.compile(r"^## (DR-(\d{3})): (.+)$", re.M)


def _records(text: str) -> list[dict]:
    out = []
    matches = list(RECORD.finditer(text))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        out.append({"id": match.group(1), "number": int(match.group(2)),
                    "title": match.group(3), "body": text[match.end():end]})
    return out


@pytest.fixture(scope="module")
def log_text() -> str:
    return DECISIONS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def record(log_text) -> dict:
    found = [r for r in _records(log_text) if "**Constraint:** RST-C14" in r["body"]]
    assert len(found) == 1, f"expected one RST-C14 record, found {len(found)}"
    return found[0]


def test_the_record_exists_and_names_both_edited_files(record):
    assert "DECISIONS.md" in record["body"]
    assert "LESSONS.md" in record["body"]


def test_it_states_that_a_typographic_pass_was_applied(record):
    assert "typographic" in record["body"].lower()


def test_it_states_which_files_it_touched_and_how_many_occurrences_in_each(record):
    body = record["body"]
    assert "**Files and counts.**" in body
    rows = re.findall(r"^\| `([^`]+)` \| ([^|]+) \|", body, re.M)
    assert len(rows) >= 10, f"only {len(rows)} per-file counts"
    named = {path for path, _ in rows}
    for required in ("DECISIONS.md", "LESSONS.md", "README.md",
                     "docs/KNOWN-MISSES.md", "gate/register.py"):
        assert required in named, f"{required} has no count"
    assert any(char.isdigit() for _, count in rows for char in count)


def test_it_states_that_no_substance_was_altered(record):
    body = record["body"]
    assert "**Substance.**" in body
    for word in ("decision", "rationale", "lesson", "count", "commentary"):
        assert word in body.lower(), f"the substance claim does not mention {word}"


def test_it_states_that_history_retains_the_original_characters_and_why(record):
    body = record["body"]
    assert "**History.**" in body
    assert "not rewritten" in body
    assert "deliberate" in body
    assert "SHA" in body or "sha" in body
    assert "RST-C8" in body


def test_the_record_is_in_the_log_it_edited():
    """A record about editing DECISIONS.md that lives elsewhere is a note."""
    assert "**Constraint:** RST-C14" in DECISIONS.read_text(encoding="utf-8")


# --- RST-C8's checks still hold over the edited log -------------------------


def test_the_log_still_parses_after_the_sweep(log_text):
    records = _records(log_text)
    assert len(records) >= 34


def test_the_numbering_still_has_no_gap(log_text):
    numbers = [r["number"] for r in _records(log_text)]
    assert numbers == list(range(1, len(numbers) + 1))


def test_every_timestamp_is_still_real_and_in_order(log_text):
    stamps = []
    for record in _records(log_text):
        found = re.search(r"\*\*Time:\*\*\s*(\S+)", record["body"])
        assert found, f"{record['id']} lost its timestamp"
        stamps.append(datetime.fromisoformat(found.group(1)))
    assert stamps == sorted(stamps)


def test_every_record_still_names_a_constraint_and_carries_a_rationale(log_text):
    for record in _records(log_text):
        assert re.search(r"\*\*Constraint:\*\* RST-C\d+", record["body"]), record["id"]
        # Anchored: DR-019 quotes "**Rationale:**" inside its own Decision,
        # and an unanchored search finds that instead of the field.
        rationale = re.search(
            r"^\*\*Rationale:\*\*\s*(.+)$", record["body"], re.M
        )
        assert rationale and len(rationale.group(1)) > 40, record["id"]
