"""RST-C6: A blocked write is visible without executing anything.

The artifact is committed, self-contained, and regenerable from the same entry
point that produces the register. It carries no volatile field at all, so the
regeneration assertion here is byte equality rather than equivalence.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from gate import cast
from gate.register import normalize_volatile

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
ARTIFACT = ROOT / cast.CAST_PATH

HEADING = re.compile(r"^#{1,6}\s")
IMAGE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)|<img[^>]+src=[\"']([^\"']+)[\"']")


@pytest.fixture(scope="module")
def readme() -> list[str]:
    return README.read_text(encoding="utf-8").splitlines()


def test_the_artifact_is_committed_in_repo(readme):
    assert ARTIFACT.exists()
    assert ARTIFACT.stat().st_size > 1000


def test_the_readme_renders_the_artifact_above_the_first_section_heading(readme):
    image_lines = [i for i, line in enumerate(readme) if IMAGE.search(line)]
    heading_lines = [i for i, line in enumerate(readme) if HEADING.match(line)]
    assert image_lines, "the README renders no image"
    assert heading_lines, "the README has no section heading"
    assert min(image_lines) < min(heading_lines), (
        "the artifact must appear above the first section heading"
    )


def test_the_placement_check_would_fail_on_a_readme_that_buries_it(tmp_path):
    """Mutate the check rather than only the subject."""
    buried = ["# Title", "", "![shot](assets/blocked-write.svg)"]
    image_lines = [i for i, line in enumerate(buried) if IMAGE.search(line)]
    heading_lines = [i for i, line in enumerate(buried) if HEADING.match(line)]
    assert min(image_lines) > min(heading_lines)


def test_the_rendered_image_is_the_committed_artifact(readme):
    first_image = next(IMAGE.search(line) for line in readme if IMAGE.search(line))
    source = first_image.group(1) or first_image.group(2)
    assert source == cast.CAST_PATH.as_posix()
    assert (ROOT / source).exists()


def test_the_image_carries_alternative_text(readme):
    line = next(line for line in readme if IMAGE.search(line))
    alt = re.match(r"!\[([^\]]*)\]", line)
    assert alt and len(alt.group(1)) > 40, "the artifact needs real alt text"


# --- self-contained ---------------------------------------------------------


SVG_NAMESPACE = "http://www.w3.org/2000/svg"


def test_the_artifact_fetches_nothing_at_render_time():
    svg = ARTIFACT.read_text(encoding="utf-8")
    for forbidden in ("<script", "href", "<image", "@import", "<foreignObject"):
        assert forbidden not in svg, f"the artifact reaches outside itself: {forbidden}"
    # The SVG namespace is a URI, not a fetch, and it is the only one permitted.
    # A substring check for "http" would flag it, and a check with a false
    # positive is worse than no check.
    assert svg.count("http") == 1
    assert SVG_NAMESPACE in svg


def test_the_no_fetch_check_catches_a_planted_remote_reference():
    planted = '<svg xmlns="http://www.w3.org/2000/svg"><image href="https://x/y.png"/></svg>'
    assert "href" in planted and planted.count("http") == 2


def test_the_artifact_is_an_svg_document():
    svg = ARTIFACT.read_text(encoding="utf-8")
    assert svg.startswith("<svg xmlns=")
    assert svg.rstrip().endswith("</svg>")


def test_the_artifact_parses_as_xml():
    import xml.etree.ElementTree as ET

    ET.parse(ARTIFACT)


# --- regenerable, and equivalent --------------------------------------------


def test_regeneration_reproduces_the_committed_artifact_byte_for_byte(tmp_path):
    regenerated = cast.render(cast.capture(tmp_path / "cast.db"), cast.cast_case().id)
    assert regenerated == ARTIFACT.read_text(encoding="utf-8")


def test_the_artifact_carries_no_volatile_field_at_all():
    """Byte equality above is only meaningful if nothing volatile was excluded."""
    svg = ARTIFACT.read_text(encoding="utf-8")
    assert normalize_volatile(svg) == svg


# --- it shows a blocked write -----------------------------------------------


def test_the_artifact_shows_the_attempt_the_refusal_and_the_unchanged_state():
    svg = ARTIFACT.read_text(encoding="utf-8")
    case = cast.cast_case()
    request_id = case.steps[-1]["args"]["request_id"]
    assert "AGENT INSTRUCTION" in svg, "the injected instruction is not shown"
    assert "approve_request" in svg, "the attempted action is not shown"
    assert "REJECTED" in svg, "the refusal is not shown"
    for code in case.expected_rejections:
        assert code in svg, f"the rejection code {code} is not shown"
    assert f"{request_id}.state = SUBMITTED" in svg, "the unchanged state is not shown"
    assert "unchanged" in svg


def test_the_artifact_is_a_view_onto_a_case_in_the_committed_set():
    case = cast.cast_case()
    assert case.gated
    assert case.cls == cast.CAST_CLASS
    assert case.id in ARTIFACT.read_text(encoding="utf-8")


def test_the_artifact_replays_the_case_it_names():
    """The header is a claim about which run produced the panel, not a label.

    An earlier version took one argument from the case and then ran a script of
    its own: a real run, but not a run of the case named on the panel.
    """
    svg = ARTIFACT.read_text(encoding="utf-8")
    case = cast.cast_case()
    assert case.id in svg
    for step in case.steps:
        assert "call" in step, f"{case.id} has a step the panel cannot show: {step}"
        assert step["call"] in svg, (
            f"the panel does not show the case's {step['call']} step"
        )
