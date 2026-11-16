import io
import json
import socket
from email.message import Message
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app import job_import, jobs
from app.job_import import JobImportError, parse_posting, public_target

pytest_plugins = ("test_library",)


def test_structured_posting_extracts_job_and_ignores_scripts() -> None:
    posting = {
        "@graph": [
            {"@type": "Organization"},
            {
                "@type": ["JobPosting"],
                "title": "Software Engineer",
                "hiringOrganization": {"name": "Acme &amp; Co"},
                "description": (
                    "<p>Build Python services.</p><ul><li>SQL experience required.</li></ul>"
                    "<script>malicious()</script>"
                ),
            },
        ]
    }
    payload = json.dumps(posting).replace("<", "\\u003c")
    result = parse_posting(
        f'<html><title>Careers</title><script type="application/ld+json">{payload}</script></html>',
        "https://example.com/job",
    )
    assert result.title == "Software Engineer"
    assert result.company == "Acme & Co"
    assert result.raw_description == "Build Python services.\nSQL experience required."
    assert "malicious" not in result.raw_description


def test_html_fallback_prefers_main_and_keeps_line_breaks() -> None:
    html = (
        "<html><head><title>Careers at Acme</title></head><body><nav>Ignore navigation</nav>"
        "<main><h1>Python Engineer</h1>"
        "<p>Develop reliable services using Python and SQL for our customers.</p>"
        "<p>Experience with production systems and strong communication required.</p>"
        "</main><footer>Ignore footer</footer></body></html>"
    )
    result = parse_posting(html, "https://example.com/job")
    assert result.title == "Python Engineer"
    assert result.company == ""
    assert "\n" in result.raw_description
    assert "Ignore" not in result.raw_description
    assert "Careers at Acme" not in result.raw_description


@pytest.mark.parametrize(
    "html",
    [
        "<title>Just a moment...</title><p>Verify your browser</p>",
        "<h1>Sign in</h1>",
        "<main>Loading…</main>",
    ],
)
def test_unreadable_pages_require_manual_fallback(html: str) -> None:
    with pytest.raises(JobImportError):
        parse_posting(html, "https://example.com/job")


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/job",
        "https://user:pass@example.com/job",
        "http://example.com:8000/job",
        "https://example.com/\r\nHost:evil",
    ],
)
def test_unsafe_urls_are_rejected_before_dns(monkeypatch, url: str) -> None:
    resolver = Mock()
    monkeypatch.setattr(socket, "getaddrinfo", resolver)
    with pytest.raises(JobImportError):
        public_target(url)
    resolver.assert_not_called()


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "169.254.169.254",
        "192.168.1.1",
        "::1",
        "fd00::1",
        "::ffff:127.0.0.1",
        "224.0.0.1",
        "0.0.0.0",
    ],
)
def test_private_and_special_destinations_are_rejected(monkeypatch, address: str) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))],
    )
    with pytest.raises(JobImportError):
        public_target("https://example.com/job")


def test_mixed_public_and_private_dns_is_rejected(monkeypatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))
            for ip in ["93.184.216.34", "127.0.0.1"]
        ],
    )
    with pytest.raises(JobImportError):
        public_target("https://example.com/job")


class Response:
    def __init__(self, body=b"", status=200, headers=None):
        self.status = status
        self.headers = Message()
        self.headers["Content-Type"] = "text/html; charset=utf-8"
        for key, value in (headers or {}).items():
            self.headers[key] = value
        self.body = io.BytesIO(body)

    def getheader(self, key, default=None):
        return self.headers.get(key, default)

    def read1(self, size):
        return self.body.read(size)


def fake_connection(monkeypatch, response):
    connection = Mock()
    connection.getresponse.return_value = response
    factory = Mock(return_value=connection)
    monkeypatch.setattr(job_import.http.client, "HTTPSConnection", factory)
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, *args, **kwargs: [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                6,
                "",
                ("127.0.0.1" if host == "private.test" else "93.184.216.34", 443),
            )
        ],
    )
    return connection, factory


def test_fetch_pins_the_checked_ip_and_does_not_send_career_data(monkeypatch) -> None:
    connection, _ = fake_connection(monkeypatch, Response(b"<html>job</html>"))
    assert job_import.fetch_page("https://example.com/job") == (
        "<html>job</html>",
        "https://example.com/job",
    )
    connector = Mock()
    monkeypatch.setattr(socket, "create_connection", connector)
    connection._create_connection(("example.com", 443))
    connector.assert_called_once_with(("93.184.216.34", 443), timeout=job_import.TIMEOUT)
    args, kwargs = connection.request.call_args
    assert args == ("GET", "/job")
    assert "body" not in kwargs
    assert "Cookie" not in kwargs["headers"]
    connection.close.assert_called_once()


def test_redirect_cannot_reach_a_private_address(monkeypatch) -> None:
    connection, factory = fake_connection(
        monkeypatch, Response(status=302, headers={"Location": "https://private.test/job"})
    )
    with pytest.raises(JobImportError):
        job_import.fetch_page("https://example.com/job")
    assert factory.call_count == 1
    connection.close.assert_called_once()


@pytest.mark.parametrize(
    "response",
    [
        Response(status=403),
        Response(b"x" * (job_import.MAX_BYTES + 1)),
        Response(headers={"Content-Encoding": "gzip"}),
    ],
)
def test_fetch_failures_and_size_limits(monkeypatch, response) -> None:
    connection, _ = fake_connection(monkeypatch, response)
    with pytest.raises(JobImportError):
        job_import.fetch_page("https://example.com/job")
    connection.close.assert_called_once()


def test_import_saves_url_and_unconfirmed_requirements_atomically(
    client: TestClient, monkeypatch
) -> None:
    monkeypatch.setattr(
        jobs,
        "import_posting",
        lambda url: job_import.ImportedJob(
            "Python Engineer", "Acme", "Python and SQL experience required.", url
        ),
    )
    response = client.post("/api/v1/jobs/import-url", json={"url": "https://example.com/job"})
    assert response.status_code == 201
    job = response.json()
    assert job["url"] == "https://example.com/job"
    assert job["source"] == "url"
    assert job["title"] == "Python Engineer"
    assert {r["text"] for r in job["requirements"]} >= {"Python", "SQL"}
    assert not any(r["confirmed"] for r in job["requirements"])
    assert job["analysis"]["method_used"] == "deterministic"
    assert (
        client.get(f"/api/v1/jobs/{job['id']}").json()["raw_description"] == job["raw_description"]
    )


def test_failed_import_does_not_create_a_job(client: TestClient, monkeypatch) -> None:
    def fail(url):
        raise JobImportError("Blocked. Paste the job text instead.")

    monkeypatch.setattr(jobs, "import_posting", fail)
    before = client.get("/api/v1/jobs").json()
    response = client.post("/api/v1/jobs/import-url", json={"url": "https://example.com/job"})
    assert response.status_code == 422
    assert "Paste the job text" in response.json()["detail"]
    assert client.get("/api/v1/jobs").json() == before
