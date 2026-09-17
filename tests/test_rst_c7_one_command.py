"""RST-C7: One command, no credential.

The clone test runs against HEAD, which is what "a clean clone" means: a reader
gets the committed tree, not the working one. It is skipped outside a git
checkout so the suite still runs from an archive.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from gate import cast, register

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "gate"

# Anything that would let the default path reach a network or a vendor.
FORBIDDEN_IMPORTS = (
    "requests",
    "urllib",
    "http.client",
    "httpx",
    "socket",
    "anthropic",
    "openai",
    "boto3",
)

CREDENTIAL_ENV = (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "GITHUB_TOKEN",
    "GH_TOKEN",
    "DATABASE_URL",
)


def _scrubbed_env(home: Path) -> dict[str, str]:
    env = {
        k: v
        for k, v in os.environ.items()
        if not any(marker in k.upper() for marker in ("KEY", "TOKEN", "SECRET", "PASSWORD"))
    }
    for name in CREDENTIAL_ENV:
        env.pop(name, None)
    env["HOME"] = str(home)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


@pytest.fixture(scope="module")
def clean_clone(tmp_path_factory):
    if not (ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    target = tmp_path_factory.mktemp("clone") / "abyss-write-gate"
    result = subprocess.run(
        ["git", "clone", "--quiet", str(ROOT), str(target)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return target


def test_the_clone_is_clean(clean_clone):
    """No run directory, no register output, nothing carried over."""
    assert not (clean_clone / "out").exists()
    assert (clean_clone / "Makefile").exists()
    assert (clean_clone / register.REGISTER_PATH).exists()


def test_one_command_takes_a_clean_clone_to_a_published_run(clean_clone, tmp_path):
    """The whole constraint, executed rather than described."""
    register_path = clean_clone / register.REGISTER_PATH
    register_path.unlink()
    assert not register_path.exists()

    result = subprocess.run(
        ["make", "demo"],
        cwd=clean_clone,
        capture_output=True,
        text=True,
        env=_scrubbed_env(tmp_path / "home"),
        timeout=300,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert register_path.exists(), "the run published no register"
    assert (clean_clone / cast.CAST_PATH).exists()
    assert "VERIFIED" in result.stdout
    assert register.parse_counts(register_path.read_text(encoding="utf-8"))["missed"] >= 1


def test_the_command_reports_the_misses_it_found(clean_clone, tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "gate", "--run-dir", str(tmp_path / "run")],
        cwd=clean_clone,
        capture_output=True,
        text=True,
        env=_scrubbed_env(tmp_path / "home"),
        timeout=300,
    )
    assert result.returncode == 0
    assert "MISS" in result.stdout
    assert "forbidden mutations landed: 0" in result.stdout


def test_no_credential_is_present_in_the_environment_the_run_sees(tmp_path):
    env = _scrubbed_env(tmp_path / "home")
    leaked = [k for k in env if any(m in k.upper() for m in ("KEY", "TOKEN", "SECRET"))]
    assert leaked == []


# --- the default path cannot reach a provider ------------------------------


def test_no_module_on_the_default_path_imports_a_network_or_vendor_library():
    offenders = {}
    for path in sorted(PACKAGE.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        hits = sorted(
            name
            for name in FORBIDDEN_IMPORTS
            if re.search(rf"^\s*(?:import|from)\s+{re.escape(name)}\b", text, re.M)
        )
        if hits:
            offenders[path.name] = hits
    assert offenders == {}, f"the default path can reach outside the process: {offenders}"


def test_the_import_scan_catches_a_planted_import(tmp_path):
    """Mutate the check."""
    planted = tmp_path / "rogue.py"
    planted.write_text("import os\nimport requests\n", encoding="utf-8")
    text = planted.read_text(encoding="utf-8")
    hits = [
        name
        for name in FORBIDDEN_IMPORTS
        if re.search(rf"^\s*(?:import|from)\s+{re.escape(name)}\b", text, re.M)
    ]
    assert hits == ["requests"]


def test_no_module_reads_a_credential_from_the_environment():
    for path in sorted(PACKAGE.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        assert "os.environ" not in text, f"{path.name} reads the environment"
        assert "getenv" not in text, f"{path.name} reads the environment"


def test_no_committed_file_contains_a_credential_shaped_string():
    listing = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=False
    ).stdout.split()
    if not listing:
        pytest.skip("not a git checkout")
    patterns = (
        r"sk-ant-[A-Za-z0-9_-]{10,}",
        r"sk-[A-Za-z0-9]{32,}",
        r"AKIA[0-9A-Z]{16}",
        r"ghp_[A-Za-z0-9]{20,}",
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    )
    for name in listing:
        path = ROOT / name
        if not path.is_file() or path.suffix in (".db",):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in patterns:
            assert not re.search(pattern, text), f"{name} looks like it carries a secret"


def test_the_repository_declares_no_runtime_dependency():
    """Standard library only on the default path."""
    for name in ("requirements.txt", "setup.py", "Pipfile", "poetry.lock"):
        assert not (ROOT / name).exists(), f"{name} would put a step before `make demo`"


# --- the entry point that WRITES refuses a near-miss argument ---------------


@pytest.mark.parametrize("flag", ["--checkk", "-c", "--regenerate", "extra"])
def test_a_near_miss_argument_writes_nothing(flag, tmp_path):
    """`python -m gate` regenerates the register and the artifact. A typo
    reaching the default path would take the write path silently."""
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    result = subprocess.run(
        [sys.executable, "-m", "gate", flag,
         "--artifacts-root", str(artifacts), "--run-dir", str(tmp_path / "run")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=_scrubbed_env(tmp_path / "home"),
        timeout=120,
    )
    assert result.returncode != 0, f"{flag} was accepted"
    assert list(artifacts.rglob("*")) == [], f"{flag} wrote something"


def test_the_control_writes_when_the_arguments_are_right(tmp_path):
    """A check that can only go red is indistinguishable from a broken one."""
    artifacts = tmp_path / "artifacts"
    result = subprocess.run(
        [sys.executable, "-m", "gate",
         "--artifacts-root", str(artifacts), "--run-dir", str(tmp_path / "run")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=_scrubbed_env(tmp_path / "home"),
        timeout=180,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (artifacts / "docs" / "KNOWN-MISSES.md").exists()
    assert (artifacts / "assets" / "blocked-write.svg").exists()
