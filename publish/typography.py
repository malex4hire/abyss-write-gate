"""The long-dash class, and a scan for it across the tracked tree.

The character is a recognised marker of machine-generated prose. This
repository's author discloses AI collaboration directly; a reader inferring it
from typography before reaching that disclosure is a different thing, and it is
not wanted.

Two properties of the check matter more than the list itself.

MATCH THE CLASS, NOT A CODEPOINT. A check for U+2014 alone stays green while a
visually identical substitute sits in the text. The class is built from the
Unicode Dash_Punctuation category with a documented exclusion list, plus the
lookalikes that are not categorised as dashes at all.

SCAN THE SOURCE, NOT THE OUTPUT. `docs/KNOWN-MISSES.md` and the SVG are
generated. Cleaning them and leaving the renderers alone means the next
`make demo` puts every occurrence back, and the check that only inspects
committed output goes green the whole way.
"""

from __future__ import annotations

import re
import subprocess
import unicodedata
from dataclasses import dataclass
from pathlib import Path

# Short dashes and hyphens. These are legitimate and stay.
#   U+002D hyphen-minus        ordinary ASCII hyphen
#   U+2010 hyphen              typographic hyphen
#   U+2011 non-breaking hyphen
#   U+2013 en dash             a range separator, excluded by the constraint
#   U+00AD soft hyphen         invisible line-break hint
#   U+FE63 small hyphen-minus
#   U+058A armenian hyphen
#   U+1400 canadian syllabics hyphen
#   U+1806 mongolian todo soft hyphen
_SHORT = frozenset(
    {0x002D, 0x2010, 0x2011, 0x2013, 0x00AD, 0xFE63, 0x058A, 0x1400, 0x1806}
)

# Long horizontal dashes that Unicode does not file under Dash_Punctuation.
#   U+2212 minus sign          renders as a long dash in most faces
#   U+2500 box drawings light horizontal
#   U+2501 box drawings heavy horizontal
#   U+30FC katakana-hiragana prolonged sound mark
_EXTRA = frozenset({0x2212, 0x2500, 0x2501, 0x30FC})


def _build_class() -> frozenset[str]:
    dashes = {
        chr(cp)
        for cp in range(0x110000)
        if unicodedata.category(chr(cp)) == "Pd" and cp not in _SHORT
    }
    return frozenset(dashes | {chr(cp) for cp in _EXTRA})


LONG_DASHES = _build_class()


@dataclass(frozen=True)
class Hit:
    path: str
    line: int
    column: int
    char: str
    text: str

    def __str__(self) -> str:
        codepoint = f"U+{ord(self.char):04X}"
        return f"{self.path}:{self.line}:{self.column} {codepoint} {self.text.strip()[:70]}"


def occurrences(text: str, path: str = "<text>") -> list[Hit]:
    hits: list[Hit] = []
    for number, line in enumerate(text.splitlines(), start=1):
        for column, char in enumerate(line, start=1):
            if char in LONG_DASHES:
                hits.append(Hit(path, number, column, char, line))
    return hits


# A source file can carry the character without containing it. A backslash-u
# escape for the em dash, written inside a Python string, is seven ASCII
# characters that render as one dash the moment the module runs. Two of those
# sat in `gate/cast.py`: invisible to a scan of the tree, and plain in the SVG
# it wrote.
_ESCAPES = (
    (re.compile(r"\\u([0-9a-fA-F]{4})"), lambda m: chr(int(m.group(1), 16))),
    (re.compile(r"\\U([0-9a-fA-F]{8})"), lambda m: chr(int(m.group(1), 16))),
    (re.compile(r"\\N\{([^}]+)\}"), lambda m: _by_name(m.group(1))),
    (re.compile(r"(?:\\x[0-9a-fA-F]{2})+"), lambda m: _from_bytes(m.group(0))),
)


def _by_name(name: str) -> str:
    try:
        return unicodedata.lookup(name)
    except KeyError:
        return ""


def _from_bytes(run: str) -> str:
    raw = bytes(int(part, 16) for part in run.split("\\x")[1:])
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return ""


def escaped_occurrences(text: str, path: str = "<text>") -> list[Hit]:
    """Escape sequences that DECODE to a long dash."""
    hits: list[Hit] = []
    for number, line in enumerate(text.splitlines(), start=1):
        for pattern, decode in _ESCAPES:
            for match in pattern.finditer(line):
                decoded = decode(match)
                for char in decoded:
                    if char in LONG_DASHES:
                        hits.append(
                            Hit(path, number, match.start() + 1, char, line)
                        )
    return hits


class UnreadableFile(RuntimeError):
    """A listed file could not be opened.

    The scan fails rather than continuing over a smaller population. A file that
    cannot be read is not a file that contains nothing: dropping it shrinks the
    denominator and reports green over content nobody looked at.
    """


@dataclass(frozen=True)
class Population:
    """What the scan actually read, and what it deliberately did not."""

    listed: int
    text: tuple[tuple[Path, str], ...]
    binary: tuple[Path, ...]

    def accounted(self) -> bool:
        return len(self.text) + len(self.binary) == self.listed


def text_population(root: Path) -> Population:
    """Every listed file, read.

    `--others --exclude-standard` includes files not yet added. A new file
    carrying the character is invisible to `ls-files` until the commit that
    tracks it, which is one commit too late to be a gate.

    Undecodable content is a binary file and is counted as skipped. Anything
    else that stops a read is an error, not a skip.
    """
    root = Path(root)
    listing = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.split()
    text: list[tuple[Path, str]] = []
    binary: list[Path] = []
    for name in listing:
        path = root / name
        if not path.is_file():
            raise UnreadableFile(
                f"{name} is listed by git but is not a readable file on disk"
            )
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            binary.append(path)
        except OSError as exc:
            raise UnreadableFile(f"{name} could not be read: {exc}") from exc
        else:
            text.append((path, content))
    population = Population(len(listing), tuple(text), tuple(binary))
    if not population.accounted():
        raise UnreadableFile(
            f"population mismatch: {len(listing)} listed, "
            f"{len(text)} read, {len(binary)} skipped as binary"
        )
    return population


def tracked_text_files(root: Path) -> list[Path]:
    return [path for path, _ in text_population(Path(root)).text]


def scan_repository(root: Path) -> list[Hit]:
    root = Path(root)
    hits: list[Hit] = []
    for path, content in text_population(root).text:
        name = path.relative_to(root).as_posix()
        hits.extend(occurrences(content, name))
        hits.extend(escaped_occurrences(content, name))
    return hits
