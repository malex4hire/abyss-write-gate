"""RST-C11 -- Publication state is asserted, not assumed.

The failure this is written against is an unreachable API reading as a
successful publication. Absence of a failure signal is not evidence of success,
so the check has three outcomes and only one of them is a pass.
"""

from __future__ import annotations

import pytest

from publish import surface
from publish.surface import FAIL, PASS, Response, UNAVAILABLE
from tests.fake_surface import API, FakeFetcher, healthy


@pytest.fixture()
def artifact_bytes():
    from pathlib import Path

    return (Path(__file__).resolve().parent.parent / "assets" / "blocked-write.svg").read_bytes()


def test_a_public_repository_passes(artifact_bytes):
    result = surface.check_visibility(healthy(artifact_bytes), "malex4hire", "abyss-write-gate")
    assert result.status == PASS
    assert "public" in result.detail


def test_a_private_repository_fails():
    """Anonymously a private repository is a 404, and a 404 is not a pass."""
    result = surface.check_visibility(FakeFetcher(), "malex4hire", "abyss-write-gate")
    assert result.status == FAIL
    assert "404" in result.detail


def test_a_repository_reported_private_fails(artifact_bytes):
    fetcher = healthy(artifact_bytes)
    fetcher.responses[API] = Response(
        200, b'{"private": true, "visibility": "private"}', "application/json"
    )
    result = surface.check_visibility(fetcher, "malex4hire", "abyss-write-gate")
    assert result.status == FAIL


def test_an_unreachable_api_is_unavailable_and_never_a_pass(artifact_bytes):
    """The whole point of the constraint."""
    fetcher = healthy(artifact_bytes)
    fetcher.unavailable.add(API)
    result = surface.check_visibility(fetcher, "malex4hire", "abyss-write-gate")
    assert result.status == UNAVAILABLE
    assert result.status != PASS
    assert not result.ok


def test_a_rate_limited_api_is_unavailable_not_a_failed_publication(artifact_bytes):
    """A 403 says nothing about visibility. Reporting it as 'not public' would
    be inventing a finding out of missing evidence."""
    fetcher = healthy(artifact_bytes)
    fetcher.responses[API] = Response(403, b'{"message": "rate limit exceeded"}')
    result = surface.check_visibility(fetcher, "malex4hire", "abyss-write-gate")
    assert result.status == UNAVAILABLE


def test_a_server_error_is_unavailable(artifact_bytes):
    fetcher = healthy(artifact_bytes)
    fetcher.responses[API] = Response(502, b"bad gateway")
    result = surface.check_visibility(fetcher, "malex4hire", "abyss-write-gate")
    assert result.status == UNAVAILABLE


def test_unparseable_json_is_unavailable_not_a_pass(artifact_bytes):
    fetcher = healthy(artifact_bytes)
    fetcher.responses[API] = Response(200, b"<html>not json</html>", "text/html")
    result = surface.check_visibility(fetcher, "malex4hire", "abyss-write-gate")
    assert result.status == UNAVAILABLE


def test_only_pass_counts_as_ok(artifact_bytes):
    assert surface.Result("x", PASS, "").ok
    assert not surface.Result("x", FAIL, "").ok
    assert not surface.Result("x", UNAVAILABLE, "").ok


def test_the_query_carries_no_credential(artifact_bytes):
    """Anonymous means anonymous: the checker must not read a token."""
    import inspect

    source = inspect.getsource(surface)
    for name in ("GITHUB_TOKEN", "GH_TOKEN", "Authorization", "getenv", "environ"):
        assert name not in source, f"the surface checker reaches for {name}"
