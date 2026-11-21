"""Tests for public HTML pages and shared page chrome."""


from urllib.parse import urlsplit

from fastapi.testclient import TestClient

from app.main import FRONTEND_URL, app


client = TestClient(app)


def test_rules_page_lists_all_eight_audit_rules():
    response = client.get("/rules")
    assert response.status_code == 200
    assert response.text.count('class="audit-rule-card"') == 8
    assert 'href="/rules"' in response.text
    assert "These eight checks are practical hints" in response.text


def test_privacy_page_documents_non_retention():
    response = client.get("/privacy")
    assert response.status_code == 200
    assert "does not retain Dockerfile text or analysis results" in response.text


def test_rust_template_is_available():
    homepage = client.get("/")
    assert 'data-template="/static/templates/rust.dockerfile"' in homepage.text

    template = client.get("/static/templates/rust.dockerfile")
    assert template.status_code == 200
    assert "FROM rust:" in template.text
    assert "cargo build --release" in template.text


def test_header_wordmark_and_input_watermark_are_available():
    homepage = client.get("/")
    assert "/static/css/landing.css?v=" in homepage.text
    assert '<a id="site-title" href="/">dockercraft</a>' in homepage.text
    assert '<div class="dockerfile-input-wrap">' in homepage.text
    assert 'id="dockerfileText" class="input-area"' in homepage.text

    stylesheet = client.get("/static/css/landing.css")
    assert ".dockerfile-input-wrap::before" in stylesheet.text
    assert "/static/logo2-ch.png" in stylesheet.text
    assert "content: '> '" in stylesheet.text
    assert "animation: blink 1s step-end infinite" in stylesheet.text

    image = client.get("/static/logo2-ch.png")
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/png"


def test_analysis_response_is_stateless():
    origin = urlsplit(FRONTEND_URL or "http://testserver")
    headers = {
        "origin": f"{origin.scheme}://{origin.netloc}",
        "host": origin.netloc,
    }
    response = client.post(
        "/api/analyze/text",
        json={"dockerfile_content": "FROM alpine:3.20\nRUN echo hello"},
        headers=headers,
    )
    assert response.status_code == 200
    assert "set-cookie" not in response.headers
