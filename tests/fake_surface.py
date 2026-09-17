"""Canned HTTP for the published-surface checks.

Not a test module. The checks are separated from the fetching precisely so
their failure modes can be exercised without a network: a gate observed only
passing against a correct tree is not a gate, and "point it at something
broken" must not require breaking the published repository to find out.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from publish.surface import Response, Unavailable

OWNER = "malex4hire"
NAME = "abyss-write-gate"

API = f"https://api.github.com/repos/{OWNER}/{NAME}"
RAW = f"https://raw.githubusercontent.com/{OWNER}/{NAME}/main"
HTML = f"https://github.com/{OWNER}/{NAME}"

RENDERED_README = (
    b'<article>\n<a href="' + RAW.encode() + b'/assets/blocked-write.svg">'
    b'<img src="https://camo.githubusercontent.com/abc" alt="A compromised agent '
    b'obeys an instruction hidden in a record"></a>\n'
    b'<h1>abyss-write-gate</h1>\n<p>An agent with write access</p>\n</article>'
)

RENDERED_REGISTER = (
    b"<article>\n<h1>Known-miss register</h1>\n"
    b"<p><strong>Read AC-603 first \xe2\x80\x94 Approve five sibling requests"
    b"</strong></p>\n<table><tr><td>Cases</td><td>24</td></tr></table>\n</article>"
)


@dataclass
class FakeFetcher:
    """Answers from a dict. Anything unlisted is a 404, which is the point."""

    responses: dict[str, Response] = field(default_factory=dict)
    unavailable: set[str] = field(default_factory=set)
    requested: list[str] = field(default_factory=list)

    def fetch(self, url: str, accept: str | None = None) -> Response:
        self.requested.append(url)
        if url in self.unavailable:
            raise Unavailable(f"fake transport refused {url}")
        if url in self.responses:
            return self.responses[url]
        return Response(status=404, body=b"Not Found")


def healthy(artifact_bytes: bytes, extra_paths: dict[str, bytes] | None = None):
    """A fetcher that answers as a correctly published public repository."""
    responses = {
        API: Response(
            200,
            b'{"private": false, "visibility": "public", "default_branch": "main"}',
            "application/json",
        ),
        f"{API}/readme": Response(200, RENDERED_README, "text/html"),
        f"{API}/contents/docs/KNOWN-MISSES.md": Response(
            200, RENDERED_REGISTER, "text/html"
        ),
        f"{RAW}/assets/blocked-write.svg": Response(
            200, artifact_bytes, "image/svg+xml"
        ),
        HTML: Response(200, b"<html>repo page</html>", "text/html"),
    }
    for path in ("docs/KNOWN-MISSES.md", "LESSONS.md", "DECISIONS.md", "README.md"):
        responses[f"{RAW}/{path}"] = Response(200, b"# a document", "text/markdown")
    for path, body in (extra_paths or {}).items():
        responses[f"{RAW}/{path}"] = Response(200, body, "text/markdown")
    return FakeFetcher(responses=responses)
