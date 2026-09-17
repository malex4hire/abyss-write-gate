"""RST-C8 -- Build log and legible history.

The log is published because the sequence is part of what is being shown. That
makes its format a thing to check rather than a thing to trust, and it makes the
absence of an elapsed-time claim in the README a thing to check too: no gate can
prove elapsed time, so the repository does not assert one.
"""

from __future__ import annotations

import re
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DECISIONS = ROOT / "DECISIONS.md"
LESSONS = ROOT / "LESSONS.md"
README = ROOT / "README.md"

RECORD = re.compile(r"^## (DR-(\d{3})) — (.+)$", re.M)
FIELD = re.compile(r"^\*\*(Time|Constraint|Decision|Rationale):\*\*\s*(.*)$", re.M)
RST_IDS = tuple(f"RST-C{n}" for n in range(1, 9))

# Phrasings that would assert how long the work took. No gate can prove elapsed
# time, so none of these belong in the README.
ELAPSED_TIME_CLAIMS = (
    r"\b\d+\s*(?:second|minute|hour|day|week|month)s?\b",
    r"\bbuilt\s+in\b",
    r"\bin\s+under\s+\w+\b",
    r"\bover\s+a\s+(?:weekend|night)\b",
    r"\bfrom\s+scratch\s+in\b",
    r"\belapsed\b",
    r"\bovernight\b",
    r"\bin\s+a\s+single\s+(?:sitting|session|day|afternoon|evening)\b",
    r"\bstart\s+to\s+finish\s+in\b",
    r"\btook\s+(?:me\s+)?\w+\s+(?:hour|day|week)",
)


def _parse_records(text: str) -> list[dict]:
    records = []
    matches = list(RECORD.finditer(text))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end() : end]
        fields = {k: v.strip() for k, v in FIELD.findall(body)}
        records.append(
            {
                "id": match.group(1),
                "number": int(match.group(2)),
                "title": match.group(3).strip(),
                "fields": fields,
                "body": body,
            }
        )
    return records


@pytest.fixture(scope="module")
def records() -> list[dict]:
    assert DECISIONS.exists(), "no build log is published"
    parsed = _parse_records(DECISIONS.read_text(encoding="utf-8"))
    assert parsed, "the build log contains no decision records"
    return parsed


# --- the log ----------------------------------------------------------------


def test_every_decision_record_carries_a_rationale(records):
    for record in records:
        rationale = record["fields"].get("Rationale", "")
        assert len(rationale) > 40, f"{record['id']} states no rationale"


def test_every_decision_record_carries_a_decision(records):
    for record in records:
        assert len(record["fields"].get("Decision", "")) > 20, f"{record['id']}"


def test_every_decision_record_carries_a_timestamp_and_a_constraint(records):
    for record in records:
        stamp = record["fields"].get("Time", "")
        datetime.fromisoformat(stamp)  # raises if it is not a real timestamp
        constraint = record["fields"].get("Constraint", "")
        assert constraint in RST_IDS, f"{record['id']} names constraint {constraint!r}"


def test_the_records_are_ordered(records):
    numbers = [r["number"] for r in records]
    assert numbers == sorted(numbers)
    assert numbers == list(range(1, len(numbers) + 1)), "the numbering has a gap"
    stamps = [datetime.fromisoformat(r["fields"]["Time"]) for r in records]
    assert stamps == sorted(stamps), "the log is not in chronological order"


def test_the_record_parser_rejects_a_record_with_no_rationale():
    """Mutate the check."""
    planted = "## DR-999 — A decision with no reason\n**Time:** 2026-01-01T00:00:00+00:00\n**Decision:** Do the thing.\n"
    parsed = _parse_records(planted)
    assert parsed and parsed[0]["fields"].get("Rationale") is None


def test_the_log_covers_every_constraint(records):
    named = {r["fields"]["Constraint"] for r in records}
    assert named == set(RST_IDS), f"constraints with no decision record: {set(RST_IDS) - named}"


def test_lessons_are_published_and_each_names_a_constraint():
    assert LESSONS.exists()
    text = LESSONS.read_text(encoding="utf-8")
    entries = re.findall(r"^## (L-\d{3}) — (.+)$", text, re.M)
    assert entries, "no lessons are published"
    assert text.count("**Constraint:**") == len(entries)


# --- the history ------------------------------------------------------------


def _git_log() -> list[str]:
    result = subprocess.run(
        ["git", "log", "--format=%s%n%b%n--%n"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return [c.strip() for c in result.stdout.split("\n--\n") if c.strip()]


def test_at_least_one_commit_names_each_constraint():
    commits = _git_log()
    if not commits:
        pytest.skip("not a git checkout")
    missing = [rst for rst in RST_IDS if not any(rst in c for c in commits)]
    assert missing == [], f"constraints with no commit: {missing}"


def test_the_history_is_incremental():
    commits = _git_log()
    if not commits:
        pytest.skip("not a git checkout")
    assert len(commits) >= len(RST_IDS), "the work landed in fewer commits than constraints"


def test_the_first_commit_is_work_rather_than_scaffolding():
    result = subprocess.run(
        ["git", "log", "--format=%H", "--reverse"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    if not result.stdout.strip():
        pytest.skip("not a git checkout")
    first = result.stdout.split()[0]
    subject = subprocess.run(
        ["git", "log", "-1", "--format=%s", first],
        cwd=ROOT, capture_output=True, text=True, check=False,
    ).stdout.strip()
    files = subprocess.run(
        ["git", "show", "--name-only", "--format=", first],
        cwd=ROOT, capture_output=True, text=True, check=False,
    ).stdout.split()
    assert "RST-C1" in subject
    assert any(f.startswith("gate/") for f in files)
    assert any(f.startswith("tests/") for f in files)


# --- no elapsed-time claim --------------------------------------------------


def elapsed_time_claims(text: str) -> list[str]:
    found = []
    for pattern in ELAPSED_TIME_CLAIMS:
        found.extend(m.group(0) for m in re.finditer(pattern, text, re.I))
    return found


def test_the_readme_asserts_no_elapsed_build_time():
    assert elapsed_time_claims(README.read_text(encoding="utf-8")) == []


def test_the_elapsed_time_check_catches_planted_claims():
    """Mutate the check: it must fire on the phrasings it is written against."""
    for planted in (
        "Built in 6 hours.",
        "The whole thing took me two days.",
        "Written over a weekend.",
        "From scratch in one sitting.",
        "Total elapsed time: small.",
        "Delivered in under a day.",
        "Built overnight.",
    ):
        assert elapsed_time_claims(planted), f"the check missed: {planted!r}"


def test_the_elapsed_time_check_does_not_fire_on_ordinary_prose():
    """A check with a false positive is worse than no check."""
    for benign in (
        "A reader gets through the whole thing in one sitting.",
        "Requests move through a five-state machine.",
        "The gate refused every one of them.",
    ):
        assert elapsed_time_claims(benign) == [], f"false positive on {benign!r}"
