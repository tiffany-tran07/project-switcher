"""Bounded public-page fetching and non-executing job-posting extraction."""

import http.client
import ipaddress
import json
import socket
import ssl
import time
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

MAX_BYTES = 2_000_000
TIMEOUT = 10
BLOCKED = {"script", "style", "nav", "footer", "header", "form", "aside", "noscript", "svg"}
VOID = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}
BREAKS = {"p", "div", "li", "br", "section", "h1", "h2", "h3", "h4", "article"}


class JobImportError(ValueError):
    pass


@dataclass
class ImportedJob:
    title: str
    company: str
    raw_description: str
    url: str


def public_target(url: str) -> tuple[str, str, int, str]:
    """Validate every destination and pin the connection to a checked address."""
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError
        if parsed.username is not None or parsed.password is not None:
            raise ValueError
        host = parsed.hostname.encode("idna").decode("ascii")
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        if port != (443 if parsed.scheme == "https" else 80):
            raise ValueError
        if any(ord(char) < 33 or ord(char) == 127 for char in url) or "\\" in url:
            raise ValueError
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        if not addresses:
            raise ValueError
        for address in addresses:
            ip = ipaddress.ip_address(address[4][0])
            if not ip.is_global or ip.is_multicast or ip.is_reserved:
                raise ValueError
        return parsed.scheme, host, port, str(addresses[0][4][0])
    except (ValueError, UnicodeError, OSError) as error:
        raise JobImportError(
            "Use a public HTTP or HTTPS job-posting URL without login credentials or a custom port."
        ) from error


def fetch_page(url: str) -> tuple[str, str]:
    deadline = time.monotonic() + 25
    for _ in range(4):
        scheme, host, port, address = public_target(url)
        parsed = urlsplit(url)
        path = urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
        connection: http.client.HTTPConnection
        if scheme == "https":
            connection = http.client.HTTPSConnection(
                host, port, timeout=TIMEOUT, context=ssl.create_default_context()
            )
        else:
            connection = http.client.HTTPConnection(host, port, timeout=TIMEOUT)
        # HTTPSConnection still uses the original hostname for SNI and certificate
        # verification, but never resolves it again when opening the socket.
        setattr(
            connection,
            "_create_connection",
            lambda *args, **kwargs: socket.create_connection((address, port), timeout=TIMEOUT),
        )
        try:
            connection.request(
                "GET",
                path,
                headers={
                    "User-Agent": "ResumeTailor/1.0 (user-requested job import)",
                    "Accept": "text/html, application/xhtml+xml",
                    "Accept-Encoding": "identity",
                },
            )
            response = connection.getresponse()
            if response.status in {301, 302, 303, 307, 308}:
                location = response.getheader("Location")
                if not location:
                    raise JobImportError(
                        "The posting returned an invalid redirect. Paste its text instead."
                    )
                url = urljoin(url, location)
                if len(url) > 1000:
                    raise JobImportError(
                        "The redirected posting URL is too long. Paste its text instead."
                    )
                continue
            if response.status != 200:
                raise JobImportError(
                    "This site blocked the request or the posting is unavailable. "
                    "Paste the job text instead."
                )
            if response.headers.get_content_type() not in {"text/html", "application/xhtml+xml"}:
                raise JobImportError(
                    "This link is not an HTML job page. Paste the job text instead."
                )
            if response.getheader("Content-Encoding", "identity").lower() != "identity":
                raise JobImportError(
                    "This site returned an unsupported page encoding. Paste the job text instead."
                )
            data = bytearray()
            while True:
                if time.monotonic() > deadline:
                    raise JobImportError(
                        "The posting took too long to load. Paste the job text instead."
                    )
                chunk = response.read1(min(65536, MAX_BYTES + 1 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > MAX_BYTES:
                    raise JobImportError(
                        "The posting page is too large. Paste the job text instead."
                    )
            charset = response.headers.get_content_charset() or "utf-8"
            try:
                return data.decode(charset, errors="replace"), url
            except LookupError:
                return data.decode("utf-8", errors="replace"), url
        except (OSError, http.client.HTTPException, UnicodeError) as error:
            raise JobImportError(
                "Could not fetch this posting. It may require a browser or login; "
                "paste its text instead."
            ) from error
        finally:
            connection.close()
    raise JobImportError("The posting redirected too many times. Paste its text instead.")


class PostingHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.body: list[str] = []
        self.main: list[str] = []
        self.title: list[str] = []
        self.heading: list[str] = []
        self.structured: list[str] = []
        self.json_script = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "script":
            self.json_script = (dict(attrs).get("type") or "").lower() == "application/ld+json"
            if self.json_script:
                self.structured.append("")
        if tag in BREAKS:
            self.handle_data("\n")
        if tag not in VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self.json_script = False
        if tag in self.stack:
            self.stack = self.stack[: len(self.stack) - 1 - self.stack[::-1].index(tag)]
        if tag in BREAKS:
            self.handle_data("\n")

    def handle_data(self, data: str) -> None:
        if self.json_script and "script" in self.stack:
            self.structured[-1] += data
        if "title" in self.stack:
            self.title.append(data)
        if "h1" in self.stack and not any(tag in BLOCKED for tag in self.stack):
            self.heading.append(data)
        if any(tag in BLOCKED or tag == "head" for tag in self.stack):
            return
        self.body.append(data)
        if "main" in self.stack or "article" in self.stack:
            self.main.append(data)


def clean_text(html: str) -> str:
    parser = PostingHTML()
    parser.feed(html)
    lines = [" ".join(unescape(line).split()) for line in "".join(parser.body).splitlines()]
    return "\n".join(line for line in lines if line).strip()


def job_postings(value: object, depth: int = 0) -> list[dict[str, Any]]:
    if depth > 12:
        return []
    if isinstance(value, list):
        return [job for item in value for job in job_postings(item, depth + 1)]
    if not isinstance(value, dict):
        return []
    kind = value.get("@type", [])
    if kind == "JobPosting" or isinstance(kind, list) and "JobPosting" in kind:
        return [value]
    return job_postings(value.get("@graph"), depth + 1) + job_postings(
        value.get("mainEntity"), depth + 1
    )


def parse_posting(html: str, url: str) -> ImportedJob:
    parser = PostingHTML()
    parser.feed(html)
    document_title = " ".join(parser.title).strip()
    if any(
        marker in document_title.lower()
        for marker in ("access denied", "just a moment", "captcha", "sign in", "security check")
    ):
        raise JobImportError(
            "This site requires browser verification or login. Paste the job text instead."
        )
    for script in parser.structured:
        try:
            postings = job_postings(json.loads(script))
        except (ValueError, RecursionError):
            continue
        for posting in postings:
            description = posting.get("description")
            title = posting.get("title")
            if not isinstance(description, str) or not isinstance(title, str):
                continue
            text = clean_text(description)
            if len(text) < 20:
                continue
            organization = posting.get("hiringOrganization", {})
            company = organization.get("name", "") if isinstance(organization, dict) else ""
            return ImportedJob(
                clean_text(title)[:200] or "Imported job",
                clean_text(company)[:200] if isinstance(company, str) else "",
                text[:100000],
                url,
            )
    title = " ".join(parser.heading).strip() or document_title
    text = "\n".join(
        line.strip() for line in "".join(parser.main or parser.body).splitlines() if line.strip()
    )
    if not title or len(text) < 100:
        raise JobImportError(
            "No readable job description was found. The site may load it with JavaScript; "
            "paste the job text instead."
        )
    return ImportedJob(title[:200], "", text[:100000], url)


def import_posting(url: str) -> ImportedJob:
    html, final_url = fetch_page(url.strip())
    return parse_posting(html, final_url)
