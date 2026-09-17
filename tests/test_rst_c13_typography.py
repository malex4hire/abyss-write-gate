"""RST-C13: No em-dash class characters on the published surface.

The gate is the control: the tracked tree is clean. Everything else in this file
exists so that the control means something, because a check observed only
passing against a clean tree is not a gate.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from publish import typography
from publish.typography import LONG_DASHES, occurrences, scan_repository

ROOT = Path(__file__).resolve().parent.parent

EM_DASH = chr(0x2014)
HORIZONTAL_BAR = chr(0x2015)
EN_DASH = chr(0x2013)
BACKSLASH = chr(92)


# --- the control ------------------------------------------------------------


def test_no_tracked_text_file_carries_a_long_dash():
    hits = scan_repository(ROOT)
    assert hits == [], "\n".join(str(h) for h in hits[:30])


def test_the_scan_actually_reads_the_tree():
    """A scan over nothing passes. Assert it found the files to read."""
    files = typography.tracked_text_files(ROOT)
    names = {p.relative_to(ROOT).as_posix() for p in files}
    assert len(files) > 25
    for required in ("README.md", "DECISIONS.md", "LESSONS.md",
                     "docs/KNOWN-MISSES.md", "assets/blocked-write.svg",
                     "gate/register.py", "cases/adversarial/01-injection-via-tool-output.json"):
        assert required in names, f"{required} was not scanned"


# --- the class, not a codepoint ---------------------------------------------


@pytest.mark.parametrize(
    "char",
    [EM_DASH, HORIZONTAL_BAR] + [chr(cp) for cp in (0x2E3A, 0x2E3B, 0xFE58, 0xFF0D, 0x2212, 0x2500)],
)
def test_every_long_dash_is_in_the_class(char):
    assert char in LONG_DASHES


@pytest.mark.parametrize(
    "char", ["-", EN_DASH] + [chr(cp) for cp in (0x2010, 0x2011, 0x00AD)]
)
def test_short_dashes_and_the_en_dash_are_not_in_the_class(char):
    assert char not in LONG_DASHES


def test_a_visually_identical_substitute_does_not_defeat_the_check():
    """A single-codepoint check for U+2014 stays green on this line."""
    text = f"A sentence {HORIZONTAL_BAR} with a lookalike."
    assert EM_DASH not in text
    assert len(occurrences(text)) == 1


def test_the_en_dash_is_left_alone_as_a_range_separator():
    assert occurrences(f"pages 10{EN_DASH}12 of the report") == []


# --- planted failures, in each of the three places --------------------------


def _plant(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def test_a_planted_dash_in_a_hand_written_file_is_caught(tmp_path):
    path = _plant(tmp_path, "README.md",
                  f"# Title\n\nA claim {EM_DASH} and its qualifier.\n")
    hits = occurrences(path.read_text(encoding="utf-8"), "README.md")
    assert len(hits) == 1
    assert hits[0].line == 3


def test_a_planted_dash_in_a_case_data_file_is_caught(tmp_path):
    payload = {"class": "x", "cases": [
        {"id": "AC-999", "commentary": f"Legal {EM_DASH} and wrong."}]}
    path = _plant(tmp_path, "cases/adversarial/99-planted.json",
                  json.dumps(payload, indent=2, ensure_ascii=False))
    hits = occurrences(path.read_text(encoding="utf-8"), "cases/adversarial/99-planted.json")
    assert len(hits) == 1


def test_a_planted_dash_in_a_renderer_is_caught(tmp_path):
    """The one that matters: a clean committed file and a dirty generator."""
    path = _plant(tmp_path, "gate/renderer.py",
                  f'def render(x):\n    return f"{{x}} {EM_DASH} unchanged"\n')
    hits = occurrences(path.read_text(encoding="utf-8"), "gate/renderer.py")
    assert len(hits) == 1


def test_the_scan_reports_every_occurrence_not_just_the_first():
    text = f"one {EM_DASH} two {HORIZONTAL_BAR} three {EM_DASH} four"
    assert len(occurrences(text)) == 3


# --- regeneration must not reintroduce them ---------------------------------


def test_regenerating_every_generated_file_leaves_the_tree_clean(tmp_path, hostile_run):
    """Cleaning the committed output and leaving the renderers alone would pass
    a scan of the tree and fail on the next `make demo`."""
    from gate import cast, register

    generated = [
        register.write(hostile_run, tmp_path / "docs" / "KNOWN-MISSES.md"),
        cast.write(tmp_path / "assets" / "blocked-write.svg", tmp_path / "cast.db"),
    ]
    hits = []
    for path in generated:
        hits.extend(occurrences(path.read_text(encoding="utf-8"), path.name))
    assert hits == [], "\n".join(str(h) for h in hits)


def test_the_regenerated_files_match_what_is_committed(tmp_path, hostile_run):
    """And the regeneration is the same one the committed copies came from."""
    from gate import cast, register
    from gate.register import normalize_volatile

    rendered = register.render(hostile_run)
    committed = (ROOT / "docs" / "KNOWN-MISSES.md").read_text(encoding="utf-8")
    assert normalize_volatile(rendered) == normalize_volatile(committed)

    svg = cast.render(cast.capture(tmp_path / "c.db"), cast.cast_case().id)
    assert svg == (ROOT / "assets" / "blocked-write.svg").read_text(encoding="utf-8")


# --- escaped, not present ---------------------------------------------------


def test_an_escape_sequence_that_decodes_to_a_long_dash_is_caught():
    """A backslash-u escape for the em dash is seven ASCII characters that
    render as one dash the moment the module runs. Two of those sat in
    `gate/cast.py`: invisible to a scan of the tree, and plain in the SVG it
    wrote."""
    source = 'Line("agent  found it ' + BACKSLASH + 'u2014 obeying it")'
    assert occurrences(source) == [], "the character is genuinely not present"
    assert len(typography.escaped_occurrences(source)) == 1


ESCAPE_FORMS = [
    BACKSLASH + "u2014",
    BACKSLASH + "U00002014",
    BACKSLASH + "N{EM DASH}",
    BACKSLASH + "xe2" + BACKSLASH + "x80" + BACKSLASH + "x94",
    BACKSLASH + "u2015",
]


@pytest.mark.parametrize("escape", ESCAPE_FORMS)
def test_every_escape_form_is_decoded(escape):
    assert len(typography.escaped_occurrences(f'x = "a {escape} b"')) == 1


@pytest.mark.parametrize("escape", [r"–", r"-", r"\x41\x42"])
def test_escapes_that_do_not_decode_to_a_long_dash_are_left_alone(escape):
    assert typography.escaped_occurrences(f'x = "a {escape} b"') == []


def test_the_repository_scan_covers_escapes_as_well_as_characters():
    assert scan_repository(ROOT) == []
    planted = 'x = "' + BACKSLASH + 'u2014"'
    assert typography.escaped_occurrences(planted, "planted.py")
