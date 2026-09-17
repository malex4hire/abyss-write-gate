"""The README artifact: a blocked write, visible without running anything.

The picture is generated from a real run. The driver reads a record, finds an
instruction addressed to it, obeys it, and the gate refuses -- and every value
on the panel (the amount, the threshold, the rejection code, the message, the
state afterwards) is read out of that run rather than typed here.

It carries no timestamp, no duration and no path, so regeneration is byte-
identical rather than merely equivalent. Nothing is fetched at render time and
nothing is hosted anywhere: the file is committed, and a reader sees it with
the page.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass
from pathlib import Path

from . import actions
from .cases import load_cases
from .fixtures import build_world
from .harness import ToolSession
from .hostile import INSTRUCTION_MARKER, extract_instructions
from .register import money

CAST_PATH = Path("assets/blocked-write.svg")

# The panel shows the first gated case of this class, selected from the data
# rather than named here. Hardcoding a case identifier would make the picture a
# second story about the set instead of a view onto it -- and there is a test
# that forbids any module from knowing a case by name.
CAST_CLASS = "injection_via_tool_output"


def cast_case():
    """The case the panel shows: the first gated case of the cast class."""
    candidates = [c for c in load_cases() if c.cls == CAST_CLASS and c.gated]
    if not candidates:
        raise LookupError(f"no gated case in class {CAST_CLASS!r}")
    return candidates[0]

COLUMNS = 84
LINE_HEIGHT = 19
FONT_SIZE = 13
CHAR_WIDTH = 7.83
PAD_X = 22
HEADER_H = 38
PAD_BOTTOM = 18

PALETTE = {
    "bg": "#0d1117",
    "chrome": "#161b22",
    "border": "#30363d",
    "prompt": "#7ee787",
    "label": "#79c0ff",
    "text": "#c9d1d9",
    "dim": "#8b949e",
    "bad": "#ff7b72",
    "warn": "#d29922",
    "good": "#7ee787",
}


@dataclass(frozen=True)
class Line:
    text: str = ""
    color: str = "text"
    bold: bool = False


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _wrap(text: str, indent: str, width: int = COLUMNS) -> list[str]:
    return textwrap.wrap(
        text, width=width, initial_indent=indent, subsequent_indent=" " * len(indent)
    ) or [indent.rstrip()]


def capture(db_path: Path | str) -> list[Line]:
    """Run the scenario and read every value on the panel out of it."""
    case = cast_case()
    request_id = case.steps[-1]["args"]["request_id"]

    store = build_world(db_path)
    session = ToolSession(store, case.principal, case_id=case.id)
    principal = session.call("whoami").result
    record = session.call("get_request", {"request_id": request_id}).result
    instructions = extract_instructions(record)
    outcome = session.call(
        instructions[0]["tool"], instructions[0].get("args", {})
    ).result
    after = store.get("Request", request_id)
    log = store.attempts(case.id)
    store.close()

    spec = actions.REGISTRY[instructions[0]["tool"]]
    marker_at = record["justification"].index(INSTRUCTION_MARKER)
    injected = " ".join(record["justification"][marker_at:].split())

    lines: list[Line] = [
        Line("$ make demo", "prompt", bold=True),
        Line(),
        Line(
            f"session    principal={principal['person_id']}   role={principal['role']}"
            f"   authority={money(principal['authority_limit_cents'])}",
            "dim",
        ),
        Line(),
        Line(f'tool       get_request(request_id="{request_id}")', "label"),
    ]
    lines.append(
        Line(
            f"  ->       {record['request_id']}  “{record['title']}”  "
            f"{money(record['amount_cents'])}  {record['state']}",
            "text",
        )
    )
    lines.append(Line("  ->       justification: untrusted free text, returned verbatim", "dim"))
    for chunk in _wrap(injected, "           "):
        lines.append(Line(chunk, "warn"))
    lines.append(Line())
    lines.append(
        Line("agent      instruction found in tool output — obeying it", "warn")
    )
    lines.append(
        Line(f'tool       {spec.name}(request_id="{request_id}")', "label")
    )
    lines.append(Line())

    codes = "  ".join(outcome["rejection_codes"])
    lines.append(Line(f"GATE       REJECTED   {codes}", "bad", bold=True))
    for chunk in _wrap(outcome["message"], "  ->       "):
        lines.append(Line(chunk, "dim"))
    lines.append(Line())
    lines.append(
        Line(
            f"datastore  {after['request_id']}.state = {after['state']}"
            f"   — unchanged, decided_by = {after['decided_by_id'] or 'none'}",
            "good",
        )
    )
    rows = f"{len(log)} row" + ("" if len(log) == 1 else "s")
    lines.append(
        Line(
            f"forensics  action_log: {rows} retained, outcome={log[-1]['outcome']}",
            "dim",
        )
    )
    return lines


def render(lines: list[Line], label: str) -> str:
    width = int(PAD_X * 2 + COLUMNS * CHAR_WIDTH)
    height = HEADER_H + PAD_BOTTOM + LINE_HEIGHT * (len(lines) + 1)
    out: list[str] = []
    add = out.append

    add(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="An agent obeys an instruction hidden in a record and the write gate rejects it">'
    )
    add(
        "<title>A compromised agent attempts a forbidden write and the gate rejects it</title>"
    )
    add(
        f'<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="10" '
        f'fill="{PALETTE["bg"]}" stroke="{PALETTE["border"]}"/>'
    )
    add(
        f'<path d="M0.5 10.5a10 10 0 0 1 10-10h{width - 21}a10 10 0 0 1 10 10v{HEADER_H - 10}'
        f'h-{width - 1}z" fill="{PALETTE["chrome"]}" stroke="{PALETTE["border"]}"/>'
    )
    for index, colour in enumerate(("#ff5f56", "#ffbd2e", "#27c93f")):
        add(f'<circle cx="{22 + index * 18}" cy="19" r="5.5" fill="{colour}"/>')
    add(
        f'<text x="{width / 2}" y="23.5" text-anchor="middle" font-size="11.5" '
        f'fill="{PALETTE["dim"]}" font-family="ui-monospace, SFMono-Regular, '
        f'Menlo, Consolas, monospace">abyss-write-gate — {_escape(label)}</text>'
    )

    add(
        f'<g font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" '
        f'font-size="{FONT_SIZE}">'
    )
    y = HEADER_H + LINE_HEIGHT
    for line in lines:
        if line.text:
            weight = ' font-weight="700"' if line.bold else ""
            add(
                f'<text x="{PAD_X}" y="{y}" xml:space="preserve" '
                f'fill="{PALETTE[line.color]}"{weight}>{_escape(line.text)}</text>'
            )
        y += LINE_HEIGHT
    add("</g>")
    add("</svg>")
    return "\n".join(out) + "\n"


def write(path: Path | str, db_path: Path | str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(capture(db_path), cast_case().id), encoding="utf-8")
    return path
