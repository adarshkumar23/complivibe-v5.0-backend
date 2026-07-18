"""Regression: EmailService.render_template must HTML-escape user-controlled
variable VALUES when rendering body_html, so a user-settable object title
(campaign/policy/finding/vendor/etc.) cannot inject markup or script into a
notification email rendered for another user.

Reported + fixed 2026-07-18 (adversarial security pass). If the escaping is ever
removed, these tests fail — the vulnerability must never silently reappear.
"""
from __future__ import annotations

from app.models.email_template import EmailTemplate
from app.services.email_service import EmailService

XSS = '<img src=x onerror=alert(document.cookie)><script>steal()</script>'


def _tmpl() -> EmailTemplate:
    # Mirrors the seeded HTML templates: static markup + user-supplied {{ vars }}.
    return EmailTemplate(
        template_key="regression",
        name="regression",
        subject_template="Attestation due: {{ campaign_title }}",
        body_text_template="Hello {{ user_name }}, campaign {{ campaign_title }}.",
        body_html_template=(
            "<p>Hello {{ user_name }},</p>"
            '<p>Campaign: <strong>{{ campaign_title }}</strong> — '
            '<a href="https://app.example/x">open</a></p>'
        ),
        allowed_variables_json=["user_name", "campaign_title"],
    )


def test_body_html_escapes_user_supplied_values(db_session):
    out = EmailService(db_session).render_template(
        _tmpl(), {"user_name": XSS, "campaign_title": "Q3 & Q4 <Review>"}
    )
    html = out["body_html"]

    # 1. the injected payload is escaped -> inert (not executable markup)
    assert XSS not in html, "raw XSS payload must not appear in body_html"
    assert "&lt;img" in html and "&lt;script" in html, "payload must be HTML-escaped"
    assert "onerror=alert" not in html or "&lt;img src=x onerror=alert" in html

    # 2. ordinary special chars in a value are also escaped
    assert "Q3 &amp; Q4 &lt;Review&gt;" in html

    # 3. the TEMPLATE'S OWN markup is preserved (only values are escaped)
    assert "<p>Hello" in html
    assert "<strong>" in html and "</strong>" in html
    assert '<a href="https://app.example/x">open</a>' in html


def test_plain_text_paths_are_not_over_escaped(db_session):
    # Escaping the plain-text subject/body would corrupt legitimate text; only the
    # HTML body is escaped. (Also documents the intended asymmetry.)
    out = EmailService(db_session).render_template(
        _tmpl(), {"user_name": XSS, "campaign_title": "A & B"}
    )
    assert "&lt;" not in (out["subject"] or "")
    assert "&lt;" not in (out["body_text"] or "")
    assert out["subject"] == "Attestation due: A & B"


def test_none_values_render_empty_not_the_string_none(db_session):
    # guard the escaping change didn't alter None handling
    tmpl = _tmpl()
    out = EmailService(db_session).render_template(
        tmpl, {"user_name": None, "campaign_title": "X"}
    )
    assert "None" not in (out["body_html"] or "")
    assert "Hello ,</p>" in out["body_html"]
