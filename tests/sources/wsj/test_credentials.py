"""Tests for WSJ credential resolution."""

import json

from web_scraper.sources.wsj.credentials import (
    get_account_path,
    load_account_credentials,
    resolve_credentials,
)


def test_load_account_credentials_from_openclaw_home(tmp_path, monkeypatch) -> None:
    openclaw_home = tmp_path / ".openclaw"
    account_path = openclaw_home / "credentials" / "wsj" / "account.json"
    account_path.parent.mkdir(parents=True)
    account_path.write_text(
        json.dumps({"email": "stored@example.com", "password": "secret"}),
        encoding="utf-8",
    )

    monkeypatch.setenv("OPENCLAW_HOME", str(openclaw_home))

    assert get_account_path() == account_path
    assert load_account_credentials() == ("stored@example.com", "secret")


def test_resolve_credentials_prefers_explicit_values(tmp_path, monkeypatch) -> None:
    openclaw_home = tmp_path / ".openclaw"
    account_path = openclaw_home / "credentials" / "wsj" / "account.json"
    account_path.parent.mkdir(parents=True)
    account_path.write_text(
        json.dumps({"email": "stored@example.com", "password": "stored-secret"}),
        encoding="utf-8",
    )

    monkeypatch.setenv("OPENCLAW_HOME", str(openclaw_home))
    monkeypatch.setenv("WSJ_EMAIL", "env@example.com")
    monkeypatch.setenv("WSJ_PASSWORD", "env-secret")

    email, password, source_path = resolve_credentials("cli@example.com", "cli-secret")

    assert (email, password) == ("cli@example.com", "cli-secret")
    assert source_path is None


def test_resolve_credentials_falls_back_to_account_file(tmp_path, monkeypatch) -> None:
    openclaw_home = tmp_path / ".openclaw"
    account_path = openclaw_home / "credentials" / "wsj" / "account.json"
    account_path.parent.mkdir(parents=True)
    account_path.write_text(
        json.dumps({"email": "stored@example.com", "password": "stored-secret"}),
        encoding="utf-8",
    )

    monkeypatch.setenv("OPENCLAW_HOME", str(openclaw_home))
    monkeypatch.delenv("WSJ_EMAIL", raising=False)
    monkeypatch.delenv("WSJ_PASSWORD", raising=False)

    email, password, source_path = resolve_credentials()

    assert (email, password) == ("stored@example.com", "stored-secret")
    assert source_path == account_path
