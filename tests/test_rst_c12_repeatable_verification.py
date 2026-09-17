"""RST-C12: Post-publication verification is repeatable.

One entry point, no arguments, no credentials. The published surface can break
later (a renamed file, a moved artifact, a rewritten README), and a one-time
manual check does not survive the next commit.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from publish import surface
from publish.__main__ import main
from tests.fake_surface import API, FakeFetcher, healthy

ROOT = Path(__file__).resolve().parent.parent
CHECK_NAMES = ("visibility", "artifact", "above_fold", "links", "register")


@pytest.fixture()
def artifact_bytes():
    return (ROOT / "assets" / "blocked-write.svg").read_bytes()


def _scrubbed_env(home: Path) -> dict[str, str]:
    env = {
        k: v
        for k, v in os.environ.items()
        if not any(m in k.upper() for m in ("KEY", "TOKEN", "SECRET", "PASSWORD"))
    }
    env["HOME"] = str(home)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


# --- the checks are one set, run together -----------------------------------


def test_run_all_reports_every_check(artifact_bytes):
    results = surface.run_all(healthy(artifact_bytes), "malex4hire", "abyss-write-gate", "main", ROOT)
    assert [r.name for r in results] == list(CHECK_NAMES)
    assert all(r.ok for r in results), [r for r in results if not r.ok]


def test_the_entry_point_exits_zero_when_every_check_passes(artifact_bytes, capsys):
    code = main([], fetcher=healthy(artifact_bytes), root=ROOT)
    out = capsys.readouterr().out
    assert code == 0
    for name in CHECK_NAMES:
        assert name in out
    assert "VERIFIED" in out


def test_the_entry_point_exits_nonzero_on_a_failure(artifact_bytes, capsys):
    fetcher = healthy(artifact_bytes)
    fetcher.responses.pop(API)
    code = main([], fetcher=fetcher, root=ROOT)
    out = capsys.readouterr().out
    assert code == 1
    assert "FAIL" in out


def test_unavailable_evidence_fails_and_reports_differently(artifact_bytes, capsys):
    """Both fail. They are not the same finding and must not read as one."""
    fetcher = healthy(artifact_bytes)
    fetcher.unavailable.add(API)
    code = main([], fetcher=fetcher, root=ROOT)
    out = capsys.readouterr().out
    assert code != 0
    assert "UNAVAILABLE" in out
    assert "evidence" in out.lower()


def test_a_failure_and_an_unavailable_produce_different_output(artifact_bytes):
    broken = healthy(artifact_bytes)
    broken.responses.pop(API)
    unreachable = healthy(artifact_bytes)
    unreachable.unavailable.add(API)
    a = surface.check_visibility(broken, "malex4hire", "abyss-write-gate")
    b = surface.check_visibility(unreachable, "malex4hire", "abyss-write-gate")
    assert a.status != b.status
    assert a.detail != b.detail


# --- the repository identity is derived, not typed --------------------------


def test_the_slug_is_derived_from_the_git_remote():
    owner, name = surface.repo_slug(ROOT)
    assert (owner, name) == ("malex4hire", "abyss-write-gate")


@pytest.mark.parametrize(
    "url,expected",
    [
        ("git@github.com:owner/name.git", ("owner", "name")),
        ("https://github.com/owner/name.git", ("owner", "name")),
        ("https://github.com/owner/name", ("owner", "name")),
        ("ssh://git@github.com/owner/name.git", ("owner", "name")),
    ],
)
def test_every_remote_form_parses(url, expected):
    assert surface.parse_remote(url) == expected


def test_an_unparseable_remote_is_an_error_not_a_guess():
    with pytest.raises(ValueError):
        surface.parse_remote("not-a-remote")


# --- it runs from a clean environment with no arguments ---------------------


def test_the_entry_point_runs_with_no_arguments_and_no_credentials(tmp_path):
    """Executed, not described. Network may or may not be present: either way
    it must complete and report every check rather than crash."""
    result = subprocess.run(
        [sys.executable, "-m", "publish"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=_scrubbed_env(tmp_path / "home"),
        timeout=180,
    )
    assert result.returncode in (0, 1), (
        f"rc={result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "Traceback" not in result.stderr, result.stderr
    for name in CHECK_NAMES:
        assert name in result.stdout, f"{name} missing from the report"
    assert re.search(r"\b(PASS|FAIL|UNAVAILABLE)\b", result.stdout)


def test_make_exposes_the_entry_point():
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert "verify-public:" in makefile
    assert "-m publish" in makefile


def test_the_verifier_is_not_on_the_gate_default_path():
    """`make demo` must stay standard-library-only and offline. The surface
    checker opens a socket, so nothing in gate/ may reach it."""
    for path in sorted((ROOT / "gate").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        assert "publish" not in text or "publish" not in text.split("\n")[0], path.name
        assert not re.search(r"^\s*(?:import|from)\s+publish\b", text, re.M), path.name


# --- arguments are parsed, not pattern-matched ------------------------------


@pytest.mark.parametrize("flag", ["--checkk", "-c", "--check", "--dry-run", "extra"])
def test_a_near_miss_argument_is_refused(flag, tmp_path, artifact_bytes, capsys):
    """A typo must not fall through to the default path and exit 0."""
    code = main([flag], fetcher=healthy(artifact_bytes), root=ROOT)
    out = capsys.readouterr().out
    assert code != 0, f"{flag} was accepted"
    for name in CHECK_NAMES:
        assert name not in out, f"{flag} ran the checks anyway"


def test_help_is_not_a_near_miss(artifact_bytes, capsys):
    """`--help` is a request, not a typo: it exits 0 and runs nothing."""
    code = main(["--help"], fetcher=healthy(artifact_bytes), root=ROOT)
    out = capsys.readouterr().out
    assert code == 0
    for name in CHECK_NAMES:
        assert name not in out


def test_the_control_still_runs_with_no_arguments(artifact_bytes, capsys):
    code = main([], fetcher=healthy(artifact_bytes), root=ROOT)
    out = capsys.readouterr().out
    assert code == 0
    assert all(name in out for name in CHECK_NAMES)


def test_a_near_miss_argument_is_refused_by_the_process(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "publish", "--checkk"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=_scrubbed_env(tmp_path / "home"),
        timeout=60,
    )
    assert result.returncode != 0
    assert "Traceback" not in result.stderr
    for name in CHECK_NAMES:
        assert name not in result.stdout
