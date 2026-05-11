"""Configuration loader for the SimpleFIN Budget App.

Sources of configuration, in priority order:

1. Environment variables: ``DATABASE_URL`` and ``SIMPLEFIN_ACCESS_URL``. These
   are how GitHub Actions and other CI runners inject secrets.
2. Streamlit ``st.secrets``: same keys. Streamlit Community Cloud exposes
   secrets through this API.
3. Local ``config.toml`` at the project root. Used for local development and
   for the in-app setup flow that persists the access URL after the user
   pastes a one-time setup token.

When ``DATABASE_URL`` is set and looks like a Postgres URL, the app stores
data in Postgres (Supabase). Otherwise it falls back to local SQLite.
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - we target 3.11+, but stay graceful
    import tomli as tomllib  # type: ignore[no-redef]

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.toml"
EXAMPLE_CONFIG_PATH = PROJECT_ROOT / "config.example.toml"


DEFAULT_CATEGORIES: tuple[str, ...] = (
    "Income",
    "Groceries",
    "Restaurants",
    "Transportation",
    "Subscriptions",
    "Rent",
    "Utilities",
    "Shopping",
    "Travel",
    "Health",
    "Transfers",
    "Fees",
    "Other",
)


@dataclass
class AppConfig:
    """In-memory view of the user's configuration."""

    db_path: Path
    access_url: str = ""
    default_categories: list[str] = field(default_factory=lambda: list(DEFAULT_CATEGORIES))
    database_url: str | None = None

    @property
    def has_access_url(self) -> bool:
        return bool(self.access_url and self.access_url.strip())

    @property
    def is_postgres(self) -> bool:
        if not self.database_url:
            return False
        scheme = urlparse(self.database_url).scheme.lower()
        return scheme.startswith("postgres")


def _ensure_config_file() -> None:
    if CONFIG_PATH.exists():
        return
    if EXAMPLE_CONFIG_PATH.exists():
        shutil.copy(EXAMPLE_CONFIG_PATH, CONFIG_PATH)
    else:
        CONFIG_PATH.write_text(
            "[simplefin]\naccess_url = \"\"\n\n[storage]\ndb_path = \"data/budget.db\"\n",
            encoding="utf-8",
        )


def _read_raw() -> dict[str, Any]:
    _ensure_config_file()
    with CONFIG_PATH.open("rb") as fh:
        return tomllib.load(fh)


def _from_streamlit_secrets(key: str) -> str | None:
    """Best-effort read from ``st.secrets`` without importing streamlit at module load."""
    try:
        import streamlit as st  # type: ignore[import-not-found]
    except Exception:
        return None
    try:
        value = st.secrets.get(key)  # type: ignore[attr-defined]
        return str(value) if value else None
    except Exception:
        return None


def _resolve(key: str, toml_value: str | None) -> str:
    env = os.environ.get(key)
    if env:
        return env.strip()
    secret = _from_streamlit_secrets(key)
    if secret:
        return secret.strip()
    return (toml_value or "").strip()


def load_config() -> AppConfig:
    raw = _read_raw()
    storage = raw.get("storage", {}) or {}
    simplefin = raw.get("simplefin", {}) or {}
    app_section = raw.get("app", {}) or {}

    db_path_value = storage.get("db_path", "data/budget.db")
    db_path = (PROJECT_ROOT / db_path_value).resolve() if not os.path.isabs(db_path_value) else Path(db_path_value)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    categories = app_section.get("default_categories") or list(DEFAULT_CATEGORIES)

    access_url = _resolve("SIMPLEFIN_ACCESS_URL", simplefin.get("access_url"))
    database_url = _resolve("DATABASE_URL", storage.get("database_url"))

    return AppConfig(
        db_path=db_path,
        access_url=access_url,
        default_categories=list(categories),
        database_url=database_url or None,
    )


def save_access_url(access_url: str) -> None:
    """Persist a freshly-claimed SimpleFIN access URL into ``config.toml``.

    Only used in local mode. On Streamlit Cloud and GitHub Actions, the access
    URL is provided via secrets/env vars and this function is a no-op safety
    net (it still writes to ``config.toml`` but the env var wins on read).
    """

    _ensure_config_file()
    raw = _read_raw()
    raw.setdefault("simplefin", {})["access_url"] = access_url.strip()
    _write_raw(raw)


def clear_access_url() -> None:
    raw = _read_raw()
    raw.setdefault("simplefin", {})["access_url"] = ""
    _write_raw(raw)


def _write_raw(data: dict[str, Any]) -> None:
    lines: list[str] = []
    storage = data.get("storage", {}) or {}
    simplefin = data.get("simplefin", {}) or {}
    app_section = data.get("app", {}) or {}

    lines.append("[simplefin]")
    lines.append(f'access_url = "{_escape(simplefin.get("access_url", ""))}"')
    lines.append("")
    lines.append("[storage]")
    lines.append(f'db_path = "{_escape(storage.get("db_path", "data/budget.db"))}"')
    if storage.get("database_url"):
        lines.append(f'database_url = "{_escape(storage.get("database_url", ""))}"')

    categories = app_section.get("default_categories")
    if categories:
        lines.append("")
        lines.append("[app]")
        formatted = ", ".join(f'"{_escape(c)}"' for c in categories)
        lines.append(f"default_categories = [{formatted}]")

    CONFIG_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
