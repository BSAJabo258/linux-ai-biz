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

import functools
import http.client
import ipaddress
import json
import os
import socket
import ssl
import time
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
DEADLINE = 45          # a whole page, however slowly it arrives (audit 2026-10-25)
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


# IPv6 forms that carry an IPv4 address inside: Python calls some of them global, but
# they can reach this computer or the home network (audit 2026-10-25).
_WRAPPED = [ipaddress.ip_network(n) for n in ("::/96", "64:ff9b::/96", "64:ff9b:1::/48")]


def _public(addr: str) -> bool:
    ip = ipaddress.ip_address(addr.split("%")[0])
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        elif any(ip in n for n in _WRAPPED):
            return False
    return ip.is_global and not ip.is_multicast


def _check(url: str, resolve: Callable[[str], list[str]]) -> str:
    """The one public address this page is read from (looked up once, here)."""
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
    return addrs[0]


# The connection goes to the address that was checked, never to a second lookup of the
# name: a name can answer "public" when checked and 127.0.0.1 a moment later (DNS
# rebinding, audit 2026-10-25). The page's own name still goes in Host and TLS (SNI).
class _PinnedHTTP(http.client.HTTPConnection):
    def __init__(self, *a: Any, pinned: str, connect: Callable[..., Any], **kw: Any):
        super().__init__(*a, **kw)
        self.pinned, self._dial = pinned, connect

    def connect(self) -> None:
        self.sock = self._dial((self.pinned, self.port), self.timeout)


class _PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, *a: Any, pinned: str, connect: Callable[..., Any], **kw: Any):
        super().__init__(*a, **kw)
        self.pinned, self._dial = pinned, connect

    def connect(self) -> None:
        sock = self._dial((self.pinned, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class _PinnedHandler(urllib.request.HTTPHandler, urllib.request.HTTPSHandler):
    def __init__(self, pinned: str, connect: Callable[..., Any]):
        urllib.request.HTTPHandler.__init__(self)
        urllib.request.HTTPSHandler.__init__(self, context=ssl.create_default_context())
        self.pinned, self.dial = pinned, connect

    def http_open(self, req):
        return self.do_open(functools.partial(_PinnedHTTP, pinned=self.pinned,
                                              connect=self.dial), req)

    def https_open(self, req):
        return self.do_open(functools.partial(_PinnedHTTPS, pinned=self.pinned,
                                              connect=self.dial), req,
                            context=self._context)


def _opener(pinned: str, connect: Callable[..., Any] | None) -> Any:
    # ProxyHandler({}): proxy settings in the environment never route around the check.
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}), _NoRedirect,
        _PinnedHandler(pinned, connect or socket.create_connection))


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
         resolve: Callable[[str], list[str]] = _resolve,
         connect: Callable[..., Any] | None = None) -> dict[str, Any]:
    _need_reason(why)
    asked = url
    try:
        return _read(url, why, audit, actor, opener, resolve, connect, asked)
    except ValueError as e:
        # A refused or failed read is audited too: that is the event worth seeing.
        _audit(audit, "web.read", actor, {"url": asked[:500], "why": why[:200],
                                          "refused": str(e)[:200]})
        raise


def _body(r: Any) -> bytes:
    """At most MAX_BYTES + 1, and never longer than DEADLINE seconds in all."""
    end, out = time.monotonic() + DEADLINE, bytearray()
    while len(out) <= MAX_BYTES:
        if time.monotonic() > end:
            raise ValueError("the page took too long to arrive")
        chunk = r.read1(65536) if hasattr(r, "read1") else r.read(MAX_BYTES + 1 - len(out))
        if not chunk:
            break
        out += chunk
    return bytes(out[:MAX_BYTES + 1])


def _read(url: str, why: str, audit: Any, actor: str, opener: Callable[..., Any] | None,
          resolve: Callable[[str], list[str]], connect: Callable[..., Any] | None,
          asked: str) -> dict[str, Any]:
    for _ in range(4):                           # the page, then at most 3 redirects
        pinned = _check(url, resolve)
        open_ = opener or _opener(pinned, connect).open
        req = urllib.request.Request(url, headers={"User-Agent": "BAU-Jarvis/1 (read-only)",
                                                   "Accept": "text/html,text/plain"})
        try:
            with open_(req, timeout=TIMEOUT) as r:
                ctype = (r.headers.get("Content-Type") or "").lower()
                body = _body(r)
            break
        except (OSError, http.client.HTTPException) as e:
            if isinstance(e, urllib.error.HTTPError):
                raise
            raise ValueError(f"the page could not be reached ({type(e).__name__})") from e
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
    _audit(audit, "web.read", actor, {"url": url, "asked": asked[:500], "why": why[:200]})
    return {"url": url, "title": " ".join(p.title.split())[:200], "text": text[:MAX_TEXT],
            "truncated": len(text) > MAX_TEXT or len(body) > MAX_BYTES}
