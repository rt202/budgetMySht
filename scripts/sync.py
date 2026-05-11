"""CLI entry point for headless syncs.

Invoke as:

    python -m scripts.sync

This is the script the macOS ``launchd`` job runs once per day. It prints a
single-line status to stdout and writes a structured ``sync_runs`` row to the
SQLite database. Exit codes:

* 0 - sync completed without API-level errors
* 1 - sync completed but SimpleFIN reported one or more institution errors
* 2 - sync failed completely (e.g. no access URL configured)
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

from app.config import load_config
from app.db import initialize
from app.ingestion import run_sync
from app.simplefin import SimpleFinError


def main() -> int:
    cfg = load_config()
    if not cfg.has_access_url:
        sys.stderr.write("No SimpleFIN access URL configured. Run the app and use Settings to connect.\n")
        return 2

    initialize(cfg)
    started = datetime.now(tz=timezone.utc).isoformat()
    try:
        result = run_sync(cfg)
    except SimpleFinError as exc:
        sys.stderr.write(f"Sync failed: {exc}\n")
        return 2

    summary = {
        "started_at": started,
        "finished_at": datetime.now(tz=timezone.utc).isoformat(),
        "status": result.status,
        "transactions_imported": result.transactions_imported,
        "transactions_updated": result.transactions_updated,
        "accounts_seen": result.accounts_seen,
        "simplefin_errors": result.simplefin_errors,
    }
    sys.stdout.write(json.dumps(summary) + "\n")
    return 0 if result.status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
