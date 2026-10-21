"""Web research for Jarvis (docs/RESEARCH.md): private search and reading pages.

Search goes only to a SearXNG on this computer (127.0.0.1:8888 by default; SearXNG binds
127.0.0.1 out of the box and must have its JSON format switched on). Reading a page is
read-only and cannot be turned against this computer or the home network: http(s) only,
every address (and every redirect) checked, size and time capped. Text comes out of the
standard library's HTML parser, no extra packages. Results are data, never instructions:
Jarvis wraps them untrusted before any model sees them. Every query and page is audited
with the reason given.
"""

from __future__ import annotations

import ipaddress
import json
import os
import socket
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from html.parser import HTMLParser
from typing import Any

DEFAULT_SEARCH = "http://127.0.0.1:8888"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
MAX_BYTES = 2_000_000
MAX_TEXT = 20_000
TIMEOUT = 20
TEXT_TYPES = ("text/html", "text/plain", "application/xhtml+xml")
NOT_RUNNING = ("the private search is not running on this computer; docs/RESEARCH.md says "
               "how to start it")


def _need_reason(why: str) -> None:
    if not (why or "").strip():
        raise ValueError("say why you are looking this up")


def _audit(audit: Any, event: str, actor: str, data: dict[str, Any]) -> None:
    if audit is not None:
        audit.append(event, actor, data)


# ------------------------------------------------------------------ search
def search(query: str, why: str, *, endpoint: str | None = None, audit: Any = None,
           actor: str = "agent:jarvis", opener: Callable[..., Any] | None = None,
           limit: int = 5) -> dict[str, Any]:
    _need_reason(why)
    base = (endpoint or os.environ.get("BAU_SEARCH_URL") or DEFAULT_SEARCH).rstrip("/")
    parts = urllib.parse.urlsplit(base)
    if parts.scheme not in ("http", "https") or parts.hostname not in LOCAL_HOSTS:
        raise ValueError(f"the search service must run on this computer, not {base}")
    query = query.strip()[:300]
    _audit(audit, "web.search", actor, {"query": query, "why": why[:200]})
    url = f"{base}/search?" + urllib.parse.urlencode({"q": query, "format": "json"})
    try:
        with (opener or urllib.request.urlopen)(urllib.request.Request(url),
                                                timeout=TIMEOUT) as r:
            data = json.loads(r.read(MAX_BYTES))
    except (urllib.error.URLError, OSError, ValueError):
        return {"query": query, "results": [], "error": NOT_RUNNING}
    results = [{"title": str(x.get("title", ""))[:200], "url": str(x.get("url", "")),
                "snippet": str(x.get("content", ""))[:400]}
               for x in data.get("results", [])[:limit]]
    return {"query": query, "results": results}


# ------------------------------------------------------------------ reading a page
def _resolve(host: str) -> list[str]:
    return [a[4][0] for a in socket.getaddrinfo(host, None)]


def _public(addr: str) -> bool:
    ip = ipaddress.ip_address(addr.split("%")[0])
    return ip.is_global and not ip.is_multicast


def _check(url: str, resolve: Callable[[str], list[str]]) -> None:
    parts = urllib.parse.urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("http", "https") or not host:
        raise ValueError("only http and https pages can be read")
    if host in LOCAL_HOSTS or host.endswith((".local", ".localhost", ".internal", ".lan")):
        raise ValueError("pages on this computer or the home network are never read")
    try:
        addrs = [str(ipaddress.ip_address(host))]
    except ValueError:
        try:
            addrs = resolve(host)
        except OSError as e:
            raise ValueError(f"{host} could not be found") from e
    if not addrs or not all(_public(a) for a in addrs):
        raise ValueError("pages on this computer or the home network are never read")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **kw):       # each redirect is checked by read()
        return None


class _Text(HTMLParser):
    SKIP = {"script", "style", "noscript", "nav", "footer", "aside", "form", "svg", "template",
            "iframe", "button", "select"}
    BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section",
             "article", "pre", "blockquote", "table", "ul", "ol"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.title = ""
        self.skip = 0
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag == "title":
            self.in_title = True
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        elif tag == "title":
            self.in_title = False
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        elif not self.skip:
            self.out.append(data)

    def text(self) -> str:
        lines = (" ".join(x.split()) for x in "".join(self.out).splitlines())
        return "\n".join(x for x in lines if x)


def read(url: str, why: str, *, audit: Any = None, actor: str = "agent:jarvis",
         opener: Callable[..., Any] | None = None,
         resolve: Callable[[str], list[str]] = _resolve) -> dict[str, Any]:
    _need_reason(why)
    open_ = opener or urllib.request.build_opener(_NoRedirect).open
    for _ in range(4):                           # the page, then at most 3 redirects
        _check(url, resolve)
        req = urllib.request.Request(url, headers={"User-Agent": "BAU-Jarvis/1 (read-only)",
                                                   "Accept": "text/html,text/plain"})
        try:
            with open_(req, timeout=TIMEOUT) as r:
                ctype = (r.headers.get("Content-Type") or "").lower()
                body = r.read(MAX_BYTES + 1)
            break
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 303, 307, 308) and e.headers.get("Location"):
                url = urllib.parse.urljoin(url, e.headers["Location"])
                continue
            raise ValueError(f"the page answered {e.code}") from e
    else:
        raise ValueError("too many redirects")
    if not ctype.startswith(TEXT_TYPES):
        raise ValueError(f"not a text page ({ctype.split(';')[0] or 'unknown type'})")
    charset = ctype.split("charset=")[-1].split(";")[0].strip() if "charset=" in ctype else "utf-8"
    try:
        html = body[:MAX_BYTES].decode(charset, errors="replace")
    except LookupError:
        html = body[:MAX_BYTES].decode("utf-8", errors="replace")
    p = _Text()
    p.feed(html)
    text = p.text()
    _audit(audit, "web.read", actor, {"url": url, "why": why[:200]})
    return {"url": url, "title": " ".join(p.title.split())[:200], "text": text[:MAX_TEXT],
            "truncated": len(text) > MAX_TEXT or len(body) > MAX_BYTES}
