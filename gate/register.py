"""The known-miss register.

Generated from the run, never maintained by hand. Every number in the document
comes from ``RunResult.counts()``, which computes each one exactly once, so a
count in the prose and a count in the machine-readable block cannot disagree.

This is the highest-value artifact in the repository. A guard with no published
blind spot has not been probed hard enough, so an empty missed set is treated as
a defect in the adversarial set rather than as a result.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .cases import MISS_REASON_CLASSES
from .runner import RunResult

REGISTER_PATH = Path("docs/KNOWN-MISSES.md")

TIMESTAMP_LINE = "**Generated:**"
COUNTS_FENCE = "```json"

# The volatile-field allowlist, as a normaliser. Everything outside it must
# reproduce byte for byte, which is what the regeneration test asserts.
_VOLATILE = (
    (re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})"), "<TIMESTAMP>"),
    (re.compile(r"\b\d+(?:\.\d+)?\s?(?:ms|s)\b(?! \w)"), "<DURATION>"),
    (re.compile(r"(?<=:)\d{4,5}\b"), "<PORT>"),
)


def normalize_volatile(text: str) -> str:
    """Blank the allowlisted volatile fields so two runs can be compared."""
    for pattern, replacement in _VOLATILE:
        text = pattern.sub(replacement, text)
    return text


def money(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def _codes(run) -> str:
    observed = sorted(set(run.observed_rejections))
    return ", ".join(f"`{c}`" for c in observed) if observed else "none"


def render(result: RunResult, now: datetime | None = None) -> str:
    counts = result.counts()
    stamp = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    lines: list[str] = []
    add = lines.append

    add("# Known-miss register")
    add("")
    add(
        "Every case in the adversarial set, labelled caught or missed, generated "
        "from the run. Nothing in this file is maintained by hand: the numbers "
        "below are computed from the run that produced it, and "
        "`tests/test_rst_c5_known_miss_register.py` asserts that regenerating it "
        "reproduces the committed copy."
    )
    add("")
    add(
        "**The missed set is the point.** A gate with no published blind spot has "
        "not been probed hard enough, so an empty missed set here is a defect in "
        "the adversarial set, not a result. There is a test that says so."
    )
    add("")
    add(f"{TIMESTAMP_LINE} {stamp} &nbsp;·&nbsp; **Regenerate:** `make demo`")
    add("")

    add("## Summary")
    add("")
    add("| | |")
    add("|---|---|")
    add(f"| Cases | {counts['cases']} |")
    add(f"| Classes | {counts['classes']} |")
    add(f"| Caught | {counts['caught']} |")
    add(f"| **Missed** | **{counts['missed']}** |")
    add(f"| Reason classes among the misses | {counts['reason_classes']} |")
    add(f"| Actions attempted against the gate | {counts['attempts']} |")
    add(f"| Gated cases (attempt violates a declared rule) | {counts['gated']} |")
    add(f"| Ungated cases (attempt violates no rule) | {counts['ungated']} |")
    add(f"| **Forbidden mutations that landed** | **{counts['forbidden_mutations_landed']}** |")
    add("")
    add(
        "A *gated* case attempts an action that violates a declared precondition; "
        "none of those land. An *ungated* case violates no precondition: it "
        "lands, and it is a register entry. The two numbers are not in tension: "
        "the first is about enforcement, the second is about what the ontology "
        "can express."
    )
    add("")

    add("## Coverage by class")
    add("")
    add("| Class | Cases | Caught | Missed |")
    add("|---|---:|---:|---:|")
    for cls, runs in sorted(result.by_class().items()):
        caught = sum(1 for r in runs if r.disposition == "caught")
        missed = sum(1 for r in runs if r.disposition == "missed")
        add(f"| `{cls}` | {len(runs)} | {caught} | {missed} |")
    add("")

    add("## Missed")
    add("")
    add(
        f"{counts['missed']} of {counts['cases']} cases produced the forbidden "
        "state of the world. Each states the class of reason the gate could not "
        "stop it."
    )
    add("")
    # The lead entry is declared in the case data, not chosen here. A register
    # whose most important finding is fourth in an alphabetical list is
    # publishing it and burying it in the same act.
    missed = sorted(result.missed, key=lambda r: (not r.case.register_lead, r.case.id))
    if missed and missed[0].case.register_lead:
        add(f"**Read {missed[0].case.id} first: {missed[0].case.title}.**")
        add("")
    for run in missed:
        case = run.case
        add(f"### {case.id}: {case.title}")
        add("")
        add(f"- **Class:** `{case.cls}`")
        add(f"- **Reason class:** `{case.miss_reason_class}`")
        add(f"- **Principal:** `{case.principal}`")
        add(f"- **Forbidden effect:** `{json.dumps(case.forbidden_effect, sort_keys=True)}`")
        add(f"- **Actions that landed:** {sum(1 for a in run.attempts if a['outcome'] == 'APPLIED')}")
        add(f"- **Evidence:** `cases/{case.id}.db` in the run directory")
        add("")
        add(f"**Why the gate cannot stop it.** {MISS_REASON_CLASSES[case.miss_reason_class]}")
        add("")
        add(case.commentary)
        add("")

    add("## Reason classes")
    add("")
    add("| Reason class | Cases | Meaning |")
    add("|---|---:|---|")
    for reason, runs in sorted(result.by_reason_class().items()):
        ids = ", ".join(r.case.id for r in runs)
        add(f"| `{reason}` | {ids} | {MISS_REASON_CLASSES[reason]} |")
    add("")

    add("## Caught")
    add("")
    add("| Case | Class | Attempt refused because | Expected |")
    add("|---|---|---|---|")
    for run in result.caught:
        expected = ", ".join(f"`{c}`" for c in run.case.expected_rejections) or "none"
        add(f"| {run.case.id} | `{run.case.cls}` | {_codes(run)} | {expected} |")
    add("")

    add("## Counts, machine-readable")
    add("")
    add(
        "Parsed by the test that asserts every number in this document matches "
        "the run it was generated from."
    )
    add("")
    add(COUNTS_FENCE)
    add(json.dumps(counts, indent=2, sort_keys=True))
    add("```")
    add("")

    return "\n".join(lines)


def parse_counts(document: str) -> dict[str, Any]:
    """Read back the machine-readable block."""
    start = document.index(COUNTS_FENCE) + len(COUNTS_FENCE)
    end = document.index("```", start)
    return json.loads(document[start:end])


def write(result: RunResult, path: Path | str, now: datetime | None = None) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(result, now=now), encoding="utf-8")
    return path
