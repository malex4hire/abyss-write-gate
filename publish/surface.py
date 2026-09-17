"""Checks against the published repository, performed anonymously.

Three outcomes, not two. `PASS` and `FAIL` are claims about the repository;
`UNAVAILABLE` is a claim about the evidence. A network error reaching the
public URL is not a broken link, an unreachable API is not a failed
publication, and neither may read as a success: absence of a failure signal is
not evidence of success.

Fetching is injected so the failure modes can be exercised without a network
and without breaking the published repository to find out whether a check would
notice.

Nothing here reads a credential. There is no token, no header, and no lookup
that could pick one up: anonymous is the point, because an authenticated fetch
answers a different question than the one a visitor asks.
"""

from __future__ import annotations

import html as html_entities
import json
import re
import subprocess
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

PASS = "PASS"
FAIL = "FAIL"
UNAVAILABLE = "UNAVAILABLE"

ARTIFACT_PATH = "assets/blocked-write.svg"
REGISTER_PATH = "docs/KNOWN-MISSES.md"
README_PATH = "README.md"

USER_AGENT = "abyss-write-gate-surface-check/1.0 (+https://github.com/malex4hire/abyss-write-gate)"

_LEAD = re.compile(r"\*\*Read (AC-\d{3}) first")
_REMOTE = re.compile(
    r"(?:git@|ssh://git@|https://)github\.com[:/]+"
    r"(?P<owner>[^/]+)/(?P<name>[^/]+?)(?:\.git)?/?$"
)
_FENCE = re.compile(r"```.*?```", re.S)
_MD_LINK = re.compile(r"!?\[[^\]]*\]\(\s*([^)\s]+)")
_IMG_TAG = re.compile(r"<img[^>]+src=[\"']([^\"']+)[\"']", re.I)


class Unavailable(Exception):
    """The evidence could not be obtained. Not a finding about the repository."""


@dataclass(frozen=True)
class Response:
    status: int
    body: bytes
    content_type: str = ""


@dataclass(frozen=True)
class Result:
    name: str
    status: str
    detail: str

    @property
    def ok(self) -> bool:
        return self.status == PASS


class Fetcher(Protocol):
    def fetch(self, url: str, accept: str | None = None) -> Response: ...


class UrllibFetcher:
    """The real transport. An HTTP status is a RESPONSE; only a transport
    failure is `Unavailable`."""

    def __init__(self, timeout: float = 20.0):
        self.timeout = timeout

    def fetch(self, url: str, accept: str | None = None) -> Response:
        headers = {"User-Agent": USER_AGENT}
        if accept:
            headers["Accept"] = accept
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as answer:
                return Response(
                    answer.status, answer.read(), answer.headers.get("Content-Type", "")
                )
        except urllib.error.HTTPError as exc:  # a real answer, including 404
            body = b""
            try:
                body = exc.read()
            except Exception:  # pragma: no cover - the body is optional
                pass
            content_type = exc.headers.get("Content-Type", "") if exc.headers else ""
            return Response(exc.code, body, content_type)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise Unavailable(f"{type(exc).__name__}: {exc}") from exc


# ---------------------------------------------------------------- identity


def parse_remote(url: str) -> tuple[str, str]:
    match = _REMOTE.search(url.strip())
    if not match:
        raise ValueError(f"not a recognised GitHub remote: {url!r}")
    return match.group("owner"), match.group("name")


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=False
    ).stdout.strip()


def repo_slug(root: Path) -> tuple[str, str]:
    """Derived from the git remote. A second copy of the slug would drift."""
    return parse_remote(_git(root, "remote", "get-url", "origin"))


def current_branch(root: Path) -> str:
    return _git(root, "rev-parse", "--abbrev-ref", "HEAD") or "main"


def api_url(owner: str, name: str) -> str:
    return f"https://api.github.com/repos/{owner}/{name}"


def raw_url(owner: str, name: str, branch: str, path: str) -> str:
    return f"https://raw.githubusercontent.com/{owner}/{name}/{branch}/{path}"


def extract_links(markdown: str) -> list[str]:
    """Link targets from prose. Fenced blocks are examples, not references."""
    prose = _FENCE.sub("", markdown)
    found: list[str] = []
    for pattern in (_MD_LINK, _IMG_TAG):
        for target in pattern.findall(prose):
            target = target.strip()
            if target.startswith("#") or target.startswith("mailto:"):
                continue
            if target not in found:
                found.append(target)
    return found


# ---------------------------------------------------------------- checks


def _status_result(name: str, status: int, missing_means_broken: bool) -> Result | None:
    if status == 200:
        return None
    if status == 404 and missing_means_broken:
        return Result(name, FAIL, f"answered {status} anonymously")
    return Result(
        name,
        UNAVAILABLE,
        f"answered {status}; the property is unknown, not disproved",
    )


def check_visibility(fetcher: Fetcher, owner: str, name: str) -> Result:
    try:
        answer = fetcher.fetch(api_url(owner, name), accept="application/vnd.github+json")
    except Unavailable as exc:
        return Result("visibility", UNAVAILABLE, f"the API could not be reached: {exc}")
    if answer.status == 404:
        return Result(
            "visibility",
            FAIL,
            "the API answered 404 to an anonymous query: the repository is not "
            "public (or does not exist)",
        )
    if answer.status != 200:
        return Result(
            "visibility",
            UNAVAILABLE,
            f"the API answered {answer.status}; visibility is unknown, not disproved",
        )
    try:
        payload = json.loads(answer.body)
    except (ValueError, TypeError):
        return Result(
            "visibility",
            UNAVAILABLE,
            "the API answer did not parse as JSON; visibility is unknown",
        )
    if payload.get("private") is False and payload.get("visibility") == "public":
        return Result("visibility", PASS, "queried anonymously: public")
    return Result(
        "visibility",
        FAIL,
        f"queried anonymously: private={payload.get('private')!r} "
        f"visibility={payload.get('visibility')!r}",
    )


def check_artifact(fetcher: Fetcher, owner: str, name: str, branch: str, root: Path) -> Result:
    url = raw_url(owner, name, branch, ARTIFACT_PATH)
    try:
        answer = fetcher.fetch(url)
    except Unavailable as exc:
        return Result("artifact", UNAVAILABLE, f"the asset host could not be reached: {exc}")
    early = _status_result("artifact", answer.status, missing_means_broken=True)
    if early:
        return early
    try:
        ET.fromstring(answer.body)
    except ET.ParseError as exc:
        return Result("artifact", FAIL, f"the published asset is not well-formed SVG: {exc}")
    committed = (Path(root) / ARTIFACT_PATH).read_bytes()
    if answer.body != committed:
        return Result(
            "artifact",
            FAIL,
            f"the published asset differs from the committed bytes "
            f"({len(answer.body)} vs {len(committed)})",
        )
    return Result(
        "artifact",
        PASS,
        f"{len(answer.body)} bytes, well-formed SVG, identical to the committed file",
    )


def resolve_src(src: str, owner: str, name: str, branch: str) -> str:
    """Turn an `<img src>` from a rendered view into something fetchable.

    Three forms occur in practice and they resolve against three different
    bases. GitHub's API render leaves the src RELATIVE; the github.com page
    rewrites it root-relative; a proxied image is absolute. Guessing one of
    them would make this check pass by accident on the other two.
    """
    src = html_entities.unescape(src.strip())
    if src.startswith(("http://", "https://")):
        return src
    if src.startswith("//"):
        return f"https:{src}"
    if src.startswith("/"):
        return f"https://github.com{src}"
    return raw_url(owner, name, branch, src)


def check_above_fold(fetcher: Fetcher, owner: str, name: str, branch: str, root: Path) -> Result:
    try:
        answer = fetcher.fetch(
            f"{api_url(owner, name)}/readme", accept="application/vnd.github.html"
        )
    except Unavailable as exc:
        return Result("above_fold", UNAVAILABLE, f"the rendered README could not be fetched: {exc}")
    early = _status_result("above_fold", answer.status, missing_means_broken=True)
    if early:
        return early
    document = answer.body.decode("utf-8", "replace")
    image = re.search(r"<img\b[^>]*\bsrc=[\"\']([^\"\']+)[\"\']", document, re.I)
    heading = re.search(r"<h[1-6]\b", document, re.I)
    if not image:
        return Result("above_fold", FAIL, "the rendered README contains no image at all")
    if heading and image.start() > heading.start():
        return Result(
            "above_fold",
            FAIL,
            "the artifact renders BELOW the first heading in the rendered view",
        )

    # An <img> tag proves a tag. Fetch the src it carries: a visitor sees a
    # broken image whenever the tag is right and the reference is not, and
    # every other check here stays green in exactly that case.
    src = image.group(1)
    target = resolve_src(src, owner, name, branch)
    try:
        asset = fetcher.fetch(target, accept="*/*")
    except Unavailable as exc:
        return Result(
            "above_fold",
            UNAVAILABLE,
            f"the rendered image source could not be reached: {src} ({exc})",
        )
    if asset.status != 200:
        return Result(
            "above_fold",
            FAIL,
            f"the rendered image source answered {asset.status}: {src}",
        )
    if not asset.content_type.lower().startswith("image/"):
        return Result(
            "above_fold",
            FAIL,
            f"the rendered image source is served as {asset.content_type!r}, "
            f"not an image: {src}",
        )
    return Result(
        "above_fold",
        PASS,
        f"renders above the first heading and its source resolves "
        f"({asset.content_type.split(';')[0]}, {len(asset.body)} bytes)",
    )


def check_links(fetcher: Fetcher, owner: str, name: str, branch: str, root: Path) -> Result:
    markdown = (Path(root) / README_PATH).read_text(encoding="utf-8")
    links = extract_links(markdown)
    if not links:
        return Result("links", FAIL, "the README contains no links, so this check proves nothing")
    broken: list[str] = []
    unreachable: list[str] = []
    for target in links:
        url = (
            target
            if target.startswith(("http://", "https://"))
            else raw_url(owner, name, branch, target)
        )
        try:
            answer = fetcher.fetch(url)
        except Unavailable as exc:
            unreachable.append(f"{target} ({exc})")
            continue
        if answer.status != 200:
            broken.append(f"{target} -> {answer.status}")
    if broken:
        # A known-broken link is a finding even if something else was
        # unreachable; the weaker signal does not suppress the stronger one.
        return Result("links", FAIL, "unresolved: " + "; ".join(broken))
    if unreachable:
        return Result(
            "links",
            UNAVAILABLE,
            "could not be reached, which is not the same as broken: "
            + "; ".join(unreachable),
        )
    return Result("links", PASS, f"{len(links)} link(s) resolved anonymously")


def check_register(fetcher: Fetcher, owner: str, name: str, branch: str, root: Path) -> Result:
    committed = (Path(root) / REGISTER_PATH).read_text(encoding="utf-8")
    lead = _LEAD.search(committed)
    if not lead:
        return Result(
            "register",
            FAIL,
            f"the committed {REGISTER_PATH} declares no lead entry to look for",
        )
    expected = lead.group(1)
    try:
        answer = fetcher.fetch(
            f"{api_url(owner, name)}/contents/{REGISTER_PATH}",
            accept="application/vnd.github.html",
        )
    except Unavailable as exc:
        return Result("register", UNAVAILABLE, f"the rendered register could not be fetched: {exc}")
    early = _status_result("register", answer.status, missing_means_broken=True)
    if early:
        return early
    html = answer.body.decode("utf-8", "replace")
    if "<table" not in html.lower():
        return Result(
            "register",
            FAIL,
            "the register did not render as markdown: no table in the rendered view",
        )
    if f"Read {expected} first" not in html:
        return Result(
            "register",
            FAIL,
            f"the rendered register does not lead with {expected}",
        )
    return Result(
        "register",
        PASS,
        f"rendered as markdown and leading with {expected}",
    )


CHECKS = (
    ("visibility", lambda f, o, n, b, r: check_visibility(f, o, n)),
    ("artifact", check_artifact),
    ("above_fold", check_above_fold),
    ("links", check_links),
    ("register", check_register),
)


def run_all(fetcher: Fetcher, owner: str, name: str, branch: str, root: Path) -> list[Result]:
    return [check(fetcher, owner, name, branch, Path(root)) for _, check in CHECKS]
