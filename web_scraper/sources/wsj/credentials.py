"""Credential resolution for WSJ login."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from .config import SOURCE_NAME


def get_account_path() -> Path:
    """Return the standard OpenClaw credential file for WSJ."""
    openclaw_home = os.environ.get("OPENCLAW_HOME")
    if openclaw_home:
        return Path(openclaw_home) / "credentials" / SOURCE_NAME / "account.json"
    return Path.home() / ".openclaw" / "credentials" / SOURCE_NAME / "account.json"


def load_account_credentials(
    account_path: Path | None = None,
) -> tuple[Optional[str], Optional[str]]:
    """Load WSJ credentials from account.json if present."""
    path = account_path or get_account_path()
    if not path.exists():
        return None, None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, None

    email = data.get("email")
    password = data.get("password")
    email = email.strip() if isinstance(email, str) else None
    password = password.strip() if isinstance(password, str) else None
    return email or None, password or None


def resolve_credentials(
    email: Optional[str] = None,
    password: Optional[str] = None,
) -> tuple[Optional[str], Optional[str], Optional[Path]]:
    """Resolve credentials from CLI args, env vars, then account.json."""
    resolved_email = email or os.environ.get("WSJ_EMAIL")
    resolved_password = password or os.environ.get("WSJ_PASSWORD")
    account_path = get_account_path()

    if resolved_email and resolved_password:
        return resolved_email, resolved_password, None

    file_email, file_password = load_account_credentials(account_path)
    if not resolved_email:
        resolved_email = file_email
    if not resolved_password:
        resolved_password = file_password

    source_path = account_path if file_email or file_password else None
    return resolved_email, resolved_password, source_path


def credentials_hint() -> str:
    """Describe where WSJ credentials should be stored."""
    return (
        f"Store credentials in {get_account_path()} "
        "or set WSJ_EMAIL / WSJ_PASSWORD."
    )
