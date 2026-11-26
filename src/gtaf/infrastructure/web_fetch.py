"""HTTP fetching for web sources (SPEC-018).

Two measured facts shape this module:

1. **TV Pirveli answers `403` to a bare client and `200` to a complete header set.** The headers below are the
   minimum a public site expects from a browser, not an attempt to look unusual.
2. **robots.txt is a preference we honour, not a puzzle to solve.** The parser implements the parts that matter
   (`Allow`, `Disallow`, `*` wildcards, longest-match, case-sensitive paths) and answers conservatively when a
   rule is ambiguous.

The fetcher also rate-limits per origin, so a nightly run does not become a burst.
"""

from __future__ import annotations

import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urlparse

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ka-GE,ka;q=0.9,en;q=0.8",
}

DEFAULT_DELAY_S = 1.0
TIMEOUT_S = 30


class FetchError(RuntimeError):
    """Raised when a page cannot be fetched."""


@dataclass(frozen=True, slots=True)
class RobotsPolicy:
    """A parsed subset of robots.txt for one origin.

    Attributes:
        rules: ``(allow, path_pattern)`` pairs; ``allow`` is True for ``Allow:``.
        crawl_delay: Declared delay in seconds, when present.
    """

    rules: tuple[tuple[bool, str], ...] = ()
    crawl_delay: float | None = None

    def allows(self, path: str) -> bool:
        """Decide whether a path may be fetched.

        Args:
            path: URL path, including the query string.

        Returns:
            True when no rule matches or the longest matching rule is an ``Allow``.

        Notes:
            Longest match wins, and a ``Disallow`` beats an ``Allow`` of the same length — the conservative
            reading. Paths are compared case-sensitively, because `robots.txt` matching is case-sensitive and
            treating `/News/` as `/news/` would both over- and under-block depending on the site.
        """
        best_length = -1
        best_allow = True
        for allow, pattern in self.rules:
            if not _matches(pattern, path):
                continue
            length = len(pattern)
            if length > best_length or (length == best_length and not allow):
                best_length = length
                best_allow = allow
        return best_allow


def _matches(pattern: str, path: str) -> bool:
    """Return True when a robots pattern matches a path.

    Args:
        pattern: Rule text, possibly containing ``*``.
        path: URL path.

    Returns:
        True on a match.
    """
    if not pattern:
        return False
    if "*" not in pattern:
        return path.startswith(pattern)
    regex = "^" + ".*".join(_escape(part) for part in pattern.split("*"))
    return _search(regex, path)


def _escape(text: str) -> str:
    """Escape a literal fragment for a regular expression."""
    import re

    return re.escape(text)


def _search(pattern: str, text: str) -> bool:
    """Search a compiled pattern against text."""
    import re

    return re.search(pattern, text) is not None


def parse_robots(text: str, *, user_agent: str = "*") -> RobotsPolicy:
    """Parse the group that applies to our user agent.

    Args:
        text: robots.txt body.
        user_agent: Agent token to match; the project sends a browser string, so ``*`` is the group that
            applies unless a site names it.

    Returns:
        The policy for that agent, or an empty policy when no group matches.

    Notes:
        Only the matching group is used, per RFC 9309. Groups listing several agents are supported.
    """
    rules: list[tuple[bool, str]] = []
    crawl_delay: float | None = None
    in_group = False
    matched_group = False

    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        field_name, _, value = line.partition(":")
        field_name = field_name.strip().lower()
        value = value.strip()

        if field_name == "user-agent":
            if matched_group and value.lower() not in {user_agent.lower(), "*"}:
                # A new group starts only after the previous one has been consumed.
                in_group = False
            else:
                in_group = value.lower() in {user_agent.lower(), "*"}
                matched_group = matched_group or in_group
            continue

        if not in_group:
            continue
        if field_name == "disallow":
            rules.append((False, value))
        elif field_name == "allow":
            rules.append((True, value))
        elif field_name == "crawl-delay":
            try:
                crawl_delay = float(value)
            except ValueError:
                crawl_delay = None

    return RobotsPolicy(rules=tuple(rules), crawl_delay=crawl_delay)


@dataclass
class BrowserFetcher:
    """Fetch pages as a browser would, politely.

    Attributes:
        delay_s: Minimum seconds between two requests to the same origin.
        _last_request: Monotonic time of the last request per origin.
        _robots: Cached policies per origin.
    """

    delay_s: float = DEFAULT_DELAY_S
    _last_request: dict[str, float] = field(default_factory=dict)
    _robots: dict[str, RobotsPolicy] = field(default_factory=dict)
    _clock: Callable[[], float] = time.monotonic
    _sleep: Callable[[float], None] = time.sleep

    def _throttle(self, origin: str) -> None:
        """Sleep so two requests to one origin are at least ``delay_s`` apart."""
        previous = self._last_request.get(origin)
        now = self._clock()
        if previous is not None:
            wait = self.delay_s - (now - previous)
            if wait > 0:
                self._sleep(wait)
        self._last_request[origin] = self._clock()

    def get(self, url: str, *, timeout: int = TIMEOUT_S) -> str:
        """Fetch a URL with browser headers.

        Args:
            url: Absolute URL.
            timeout: Request timeout in seconds.

        Returns:
            Response body as text.

        Raises:
            FetchError: On any transport or HTTP failure, with the reason preserved.

        Notes:
            A 403 is reported as itself rather than hidden: measured 2026-11-26, a bare client gets 403 on
            every path of one source while a browser header set gets 200, and confusing the two would look
            like a site-wide outage.
        """
        origin = _origin(url)
        self._throttle(origin)
        request = urllib.request.Request(url, headers=BROWSER_HEADERS)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return str(response.read().decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as exc:
            raise FetchError(f"HTTP {exc.code} for {url}") from exc
        except Exception as exc:
            raise FetchError(f"{type(exc).__name__} for {url}") from exc

    def robots(self, url: str) -> RobotsPolicy:
        """Return the robots policy for a URL's origin.

        Args:
            url: Any URL on the origin.

        Returns:
            The policy; an empty (allow-all) policy when robots.txt is missing or unreadable.

        Notes:
            RFC 9309 permits treating an absent robots.txt as allow-all, and a site that hides the file from
            us cannot be assumed to forbid everything.
        """
        origin = _origin(url)
        if origin in self._robots:
            return self._robots[origin]
        try:
            text = self.get(f"{origin}/robots.txt")
        except FetchError:
            policy = RobotsPolicy()
        else:
            policy = parse_robots(text)
        self._robots[origin] = policy
        return policy

    def allowed(self, url: str) -> bool:
        """Decide whether robots.txt permits fetching this URL.

        Args:
            url: Absolute URL.

        Returns:
            True when allowed.
        """
        return self.robots(url).allows(_path(url))


def _origin(url: str) -> str:
    """Return ``scheme://host`` for a URL."""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _path(url: str) -> str:
    """Return the path plus query for a URL."""
    parsed = urlparse(url)
    return parsed.path + (f"?{parsed.query}" if parsed.query else "")
