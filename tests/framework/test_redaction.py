import json

import pytest

from utils.reporting.evidence import redact_html
from utils.reporting.redaction import redact, redact_text, redact_url


@pytest.mark.parametrize(
    "markup",
    [
        '<input type="text" name="password" value="private-secret">',
        '<input id="userPassword" value="private-secret">',
        '<textarea name="api_token">private-secret &amp; more</textarea>',
        '<textarea id="client_secret">private-secret',
    ],
)
def test_sensitive_field_names_and_textareas_are_masked(markup):
    result = redact_html("<p>Public text</p>" + markup)
    assert result.startswith("<p>Public text</p>")
    assert "private-secret" not in result
    assert "[redacted]" in result


def test_url_credentials_and_secret_query_values_are_masked():
    source = "https://alice:private-pass@example.test/path?token=private-token&view=public#access_token=fragment-secret"
    result = redact_url(source)
    assert all(
        value not in result
        for value in ("alice", "private-pass", "private-token", "fragment-secret")
    )
    assert "example.test/path" in result and "view=public" in result


def test_nested_capabilities_and_console_secrets_are_masked():
    source = {
        "proxy": {"password": "proxy-secret", "server": "http://user:proxy-auth@example.test"},
        "logs": [
            {"message": "Authorization: Bearer bearer-secret"},
            {"message": 'password="two word secret"'},
        ],
        "name": "public",
    }
    result = json.dumps(redact(source))
    assert all(
        value not in result
        for value in ("proxy-secret", "proxy-auth", "bearer-secret", "two word secret")
    )
    assert "public" in result


def test_public_url_and_unlabelled_text_are_kept():
    assert redact_url("https://example.test/?page=2") == "https://example.test/?page=2"
    assert redact_text("Public response 200") == "Public response 200"
