import pytest

from config import (
    DEFAULT_CORS_ORIGINS,
    _normalize_database_url,
    _parse_cors_origins,
)


@pytest.mark.parametrize(
    ("provider_url", "application_url"),
    [
        (
            "postgresql://docpilot:secret@database.internal/docpilot",
            "postgresql+psycopg://docpilot:secret@database.internal/docpilot",
        ),
        (
            "postgres://docpilot:secret@database.internal/docpilot",
            "postgresql+psycopg://docpilot:secret@database.internal/docpilot",
        ),
    ],
)
def test_normalize_database_url_uses_psycopg_driver(provider_url, application_url):
    assert _normalize_database_url(provider_url) == application_url


def test_normalize_database_url_preserves_explicit_driver():
    database_url = "postgresql+psycopg://docpilot:secret@database/docpilot"

    assert _normalize_database_url(database_url) == database_url


def test_parse_cors_origins_normalizes_configured_origins():
    raw_origins = " https://app.example.com/ ,https://admin.example.com,, null "

    assert _parse_cors_origins(raw_origins) == [
        "https://app.example.com",
        "https://admin.example.com",
        "null",
    ]


def test_parse_cors_origins_preserves_local_defaults_when_unset():
    assert _parse_cors_origins(None) == list(DEFAULT_CORS_ORIGINS)
