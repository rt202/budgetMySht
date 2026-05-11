"""SimpleFIN Bridge client.

Implements the two operations we need:

1. Exchange a one-time setup token for a long-lived access URL.
2. Fetch accounts and transactions from the access URL.

Reference: https://beta-bridge.simplefin.org/info/developers
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import requests

DEFAULT_TIMEOUT = 30


class SimpleFinError(RuntimeError):
    """Raised when SimpleFIN returns an error or the response is malformed."""


@dataclass(frozen=True)
class AccessUrl:
    """Parsed SimpleFIN access URL containing embedded basic auth credentials."""

    raw: str
    username: str
    password: str
    base_url: str

    @classmethod
    def parse(cls, raw: str) -> "AccessUrl":
        raw = raw.strip()
        if not raw:
            raise SimpleFinError("Empty access URL")
        parts = urlsplit(raw)
        if not parts.scheme or not parts.netloc:
            raise SimpleFinError("Access URL is not a valid URL")
        if "@" not in parts.netloc:
            raise SimpleFinError("Access URL is missing embedded credentials")
        auth, host = parts.netloc.split("@", 1)
        if ":" not in auth:
            raise SimpleFinError("Access URL credentials must be username:password")
        username, password = auth.split(":", 1)
        clean = urlunsplit((parts.scheme, host, parts.path, "", ""))
        return cls(raw=raw, username=username, password=password, base_url=clean.rstrip("/"))


def claim_access_url(setup_token: str, *, timeout: int = DEFAULT_TIMEOUT) -> str:
    """Exchange a one-time setup token for an access URL.

    The setup token is base64-encoded and decodes to the claim URL. A SimpleFIN
    setup token can only be claimed once.
    """

    token = setup_token.strip()
    if not token:
        raise SimpleFinError("Setup token is empty")
    try:
        claim_url = base64.b64decode(token).decode("utf-8").strip()
    except Exception as exc:  # noqa: BLE001 - any decoding error means bad input
        raise SimpleFinError("Setup token is not valid base64") from exc
    if not claim_url.lower().startswith("http"):
        raise SimpleFinError("Decoded claim URL does not look like a URL")

    response = requests.post(claim_url, headers={"Content-Length": "0"}, timeout=timeout)
    if response.status_code != 200:
        raise SimpleFinError(
            f"Failed to claim setup token (HTTP {response.status_code}): {response.text.strip()[:200]}"
        )
    access_url = response.text.strip()
    if not access_url:
        raise SimpleFinError("SimpleFIN returned an empty access URL")
    AccessUrl.parse(access_url)
    return access_url


def fetch_accounts(
    access_url: str,
    *,
    start_date: int | None = None,
    end_date: int | None = None,
    pending: bool = True,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Fetch ``/accounts`` JSON. Dates are unix seconds.

    Returns the raw JSON dict as supplied by SimpleFIN, which has the shape::

        {
            "errors": [...],
            "accounts": [
                {
                    "id": "...",
                    "name": "...",
                    "currency": "USD",
                    "balance": "123.45",
                    "available-balance": "120.00",
                    "balance-date": 1701234567,
                    "org": {"name": "...", "domain": "..."},
                    "transactions": [...]
                },
                ...
            ]
        }
    """

    parsed = AccessUrl.parse(access_url)
    params: dict[str, Any] = {"version": "2"}
    if start_date is not None:
        params["start-date"] = int(start_date)
    if end_date is not None:
        params["end-date"] = int(end_date)
    if pending:
        params["pending"] = "1"

    response = requests.get(
        f"{parsed.base_url}/accounts",
        params=params,
        auth=(parsed.username, parsed.password),
        timeout=timeout,
    )
    if response.status_code != 200:
        raise SimpleFinError(
            f"SimpleFIN /accounts returned HTTP {response.status_code}: {response.text.strip()[:200]}"
        )
    try:
        return response.json()
    except ValueError as exc:
        raise SimpleFinError("SimpleFIN response was not valid JSON") from exc
