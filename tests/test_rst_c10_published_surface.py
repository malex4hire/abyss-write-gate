"""RST-C10 -- The published surface is verified anonymously.

Every check here is exercised twice: against a surface that is correct, and
against one deliberately broken. A check that has only been observed passing
against a correct tree is not a gate.

The transport is injected, so "deliberately broken" does not mean breaking the
published repository to find out whether the check would notice.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from publish import surface
from publish.surface import FAIL, PASS, Response, UNAVAILABLE
from tests.fake_surface import API, RAW, FakeFetcher, healthy

ROOT = Path(__file__).resolve().parent.parent
OWNER, NAME, BRANCH = "malex4hire", "abyss-write-gate", "main"


@pytest.fixture()
def artifact_bytes():
    return (ROOT / "assets" / "blocked-write.svg").read_bytes()


@pytest.fixture()
def fetcher(artifact_bytes):
    return healthy(artifact_bytes)


def _run(check, fetcher):
    return check(fetcher, OWNER, NAME, BRANCH, ROOT)


# --- link extraction --------------------------------------------------------


def test_links_are_extracted_from_prose_and_not_from_code_fences():
    markdown = (
        "![alt](assets/a.svg)\n"
        "See [the register](docs/KNOWN-MISSES.md) and [lessons](LESSONS.md).\n"
        "```\ngit clone https://github.com/someone/else\n"
        "[not a link](nope/should-not-be-followed.md)\n```\n"
        "An [anchor](#section) and a [mail](mailto:a@b.c).\n"
    )
    links = surface.extract_links(markdown)
    assert "assets/a.svg" in links
    assert "docs/KNOWN-MISSES.md" in links
    assert "LESSONS.md" in links
    assert "nope/should-not-be-followed.md" not in links, "a fenced block is not prose"
    assert not any(l.startswith("#") for l in links)
    assert not any(l.startswith("mailto:") for l in links)


def test_the_readme_actually_contains_links_to_check():
    """A link checker over a README with no links passes having done nothing."""
    links = surface.extract_links((ROOT / "README.md").read_text(encoding="utf-8"))
    assert len(links) >= 3, f"only found {links}"
    assert "assets/blocked-write.svg" in links
    assert "docs/KNOWN-MISSES.md" in links


# --- the above-fold artifact ------------------------------------------------


def test_the_artifact_is_reachable_and_matches_what_was_committed(fetcher):
    result = _run(surface.check_artifact, fetcher)
    assert result.status == PASS


def test_a_missing_artifact_fails(fetcher):
    del fetcher.responses[f"{RAW}/assets/blocked-write.svg"]
    result = _run(surface.check_artifact, fetcher)
    assert result.status == FAIL
    assert "404" in result.detail


def test_an_artifact_that_differs_from_the_committed_bytes_fails(fetcher):
    """A moved or stale asset serves 200 and is still wrong."""
    fetcher.responses[f"{RAW}/assets/blocked-write.svg"] = Response(
        200, b'<svg xmlns="http://www.w3.org/2000/svg"></svg>', "image/svg+xml"
    )
    result = _run(surface.check_artifact, fetcher)
    assert result.status == FAIL
    assert "differs" in result.detail


def test_an_artifact_that_is_not_valid_svg_fails(fetcher):
    fetcher.responses[f"{RAW}/assets/blocked-write.svg"] = Response(
        200, b"<svg unclosed", "image/svg+xml"
    )
    result = _run(surface.check_artifact, fetcher)
    assert result.status == FAIL


def test_an_unreachable_host_is_unavailable_not_a_broken_link(fetcher):
    """A network error reaching the public URL is not a broken link."""
    fetcher.unavailable.add(f"{RAW}/assets/blocked-write.svg")
    result = _run(surface.check_artifact, fetcher)
    assert result.status == UNAVAILABLE
    assert "broken" not in result.detail.lower()


# --- the rendered README ----------------------------------------------------


def test_the_artifact_renders_above_the_first_heading_in_the_rendered_view(fetcher):
    result = _run(surface.check_above_fold, fetcher)
    assert result.status == PASS


def test_an_image_below_the_first_heading_fails(fetcher):
    """The local test asserts this about markdown source. This asserts it about
    what GitHub actually rendered."""
    fetcher.responses[f"{API}/readme"] = Response(
        200, b"<article><h1>title</h1><img src='x'></article>", "text/html"
    )
    result = _run(surface.check_above_fold, fetcher)
    assert result.status == FAIL


def test_a_rendered_readme_with_no_image_fails(fetcher):
    fetcher.responses[f"{API}/readme"] = Response(
        200, b"<article><h1>title</h1><p>prose</p></article>", "text/html"
    )
    result = _run(surface.check_above_fold, fetcher)
    assert result.status == FAIL


def test_a_readme_that_did_not_render_is_unavailable(fetcher):
    fetcher.unavailable.add(f"{API}/readme")
    assert _run(surface.check_above_fold, fetcher).status == UNAVAILABLE


# --- every link resolves ----------------------------------------------------


def test_every_readme_link_resolves(fetcher):
    result = _run(surface.check_links, fetcher)
    assert result.status == PASS, result.detail


def test_a_broken_relative_link_fails(fetcher, tmp_path):
    """Point it at something broken and require it to notice."""
    readme = tmp_path / "README.md"
    readme.write_text(
        "![a](assets/blocked-write.svg)\n\n# t\n\n[gone](docs/DOES-NOT-EXIST.md)\n",
        encoding="utf-8",
    )
    result = surface.check_links(fetcher, OWNER, NAME, BRANCH, tmp_path)
    assert result.status == FAIL
    assert "docs/DOES-NOT-EXIST.md" in result.detail


def test_a_link_whose_host_is_unreachable_is_unavailable(fetcher, tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text("[register](docs/KNOWN-MISSES.md)\n", encoding="utf-8")
    fetcher.unavailable.add(f"{RAW}/docs/KNOWN-MISSES.md")
    result = surface.check_links(fetcher, OWNER, NAME, BRANCH, tmp_path)
    assert result.status == UNAVAILABLE
    assert "DOES-NOT-EXIST" not in result.detail


# --- the register is readable, rendered -------------------------------------


def test_the_register_renders_as_markdown_not_as_source(fetcher):
    result = _run(surface.check_register, fetcher)
    assert result.status == PASS


def test_a_register_served_as_plain_source_fails(fetcher):
    """Readable 'in the rendered view, not only as source' is the requirement."""
    fetcher.responses[f"{API}/contents/docs/KNOWN-MISSES.md"] = Response(
        200, b"# Known-miss register\n\n| Cases | 24 |\n", "text/plain"
    )
    result = _run(surface.check_register, fetcher)
    assert result.status == FAIL


def test_a_register_missing_its_lead_entry_fails(fetcher):
    fetcher.responses[f"{API}/contents/docs/KNOWN-MISSES.md"] = Response(
        200, b"<article><h1>Known-miss register</h1><table></table></article>", "text/html"
    )
    result = _run(surface.check_register, fetcher)
    assert result.status == FAIL
    assert "AC-603" in result.detail


def test_an_unreachable_register_is_unavailable(fetcher):
    fetcher.unavailable.add(f"{API}/contents/docs/KNOWN-MISSES.md")
    assert _run(surface.check_register, fetcher).status == UNAVAILABLE


# --- the rendered image src actually resolves -------------------------------
#
# The gap this closes: an <img> above the first heading proves a tag is there,
# and a reachable raw asset proves the file is there. Neither proves the SRC
# THE RENDERED VIEW CARRIES resolves to it. A visitor sees a broken image in
# exactly that case, and both checks stay green.


def test_the_rendered_image_source_is_fetched_not_assumed(fetcher):
    result = _run(surface.check_above_fold, fetcher)
    assert result.status == PASS
    assert f"{RAW}/assets/blocked-write.svg" in fetcher.requested, (
        "the check never fetched the src it found"
    )


def test_a_rendered_image_source_that_404s_fails(fetcher):
    fetcher.responses[f"{API}/readme"] = Response(
        200, b'<article><img src="assets/moved-away.svg"><h1>t</h1></article>', "text/html"
    )
    result = _run(surface.check_above_fold, fetcher)
    assert result.status == FAIL
    assert "moved-away.svg" in result.detail


def test_a_rendered_image_source_serving_non_image_content_fails(fetcher):
    fetcher.responses[f"{RAW}/assets/blocked-write.svg"] = Response(
        200, b"<html>not found, have a page instead</html>", "text/html"
    )
    result = _run(surface.check_above_fold, fetcher)
    assert result.status == FAIL
    assert "image" in result.detail


def test_an_unreachable_image_source_is_unavailable_not_broken(fetcher):
    fetcher.unavailable.add(f"{RAW}/assets/blocked-write.svg")
    result = _run(surface.check_above_fold, fetcher)
    assert result.status == UNAVAILABLE


@pytest.mark.parametrize(
    "src,expected",
    [
        ("assets/blocked-write.svg", f"{RAW}/assets/blocked-write.svg"),
        ("/malex4hire/abyss-write-gate/raw/main/x.svg",
         "https://github.com/malex4hire/abyss-write-gate/raw/main/x.svg"),
        ("https://camo.githubusercontent.com/abc", "https://camo.githubusercontent.com/abc"),
        ("assets/a%20b.svg", f"{RAW}/assets/a%20b.svg"),
    ],
)
def test_every_src_form_a_renderer_emits_is_resolved(src, expected):
    assert surface.resolve_src(src, OWNER, NAME, BRANCH) == expected


def test_an_html_escaped_src_is_unescaped_before_fetching():
    assert surface.resolve_src("https://x/y?a=1&amp;b=2", OWNER, NAME, BRANCH) == (
        "https://x/y?a=1&b=2"
    )
