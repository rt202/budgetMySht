"""SimpleFIN -> SQLite import pipeline.

Responsibilities:

* Call SimpleFIN ``/accounts`` for the configured access URL.
* Persist raw payloads in ``transactions_raw`` for auditability.
* Upsert normalized rows into ``accounts`` and ``transactions`` without
  clobbering manual category overrides stored in ``transaction_overrides``.
* Re-run the classifier so newly-imported transactions get a suggested
  category when a rule matches.
* Record a ``sync_runs`` row with status, counts, and any error.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from .classifier import classify, load_rules
from .config import AppConfig, load_config
from .db import Conn, connect, initialize
from .simplefin import SimpleFinError, fetch_accounts


@dataclass
class SyncResult:
    sync_run_id: int
    status: str
    transactions_imported: int
    transactions_updated: int
    accounts_seen: int
    error: str | None
    simplefin_errors: list[str]


def _to_float(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_iso(value: Any) -> str | None:
    if value is None or value == "":
        return None
    try:
        ts = int(value)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _start_run(conn: Conn) -> int:
    cursor = conn.execute(
        "INSERT INTO sync_runs(status) VALUES ('running') RETURNING id"
    )
    row = cursor.fetchone()
    return int(row["id"])


def _finish_run(
    conn: Conn,
    run_id: int,
    *,
    status: str,
    transactions_imported: int,
    transactions_updated: int,
    accounts_seen: int,
    error: str | None,
) -> None:
    conn.execute(
        """
        UPDATE sync_runs
        SET finished_at = CURRENT_TIMESTAMP,
            status = ?,
            transactions_imported = ?,
            transactions_updated = ?,
            accounts_seen = ?,
            error = ?
        WHERE id = ?
        """,
        (status, transactions_imported, transactions_updated, accounts_seen, error, run_id),
    )


def _upsert_account(conn: Conn, account: dict[str, Any]) -> None:
    org = account.get("org") or {}
    conn.execute(
        """
        INSERT INTO accounts(id, org_name, org_domain, name, currency, balance, available_balance, balance_date, last_synced_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(id) DO UPDATE SET
            org_name = excluded.org_name,
            org_domain = excluded.org_domain,
            name = excluded.name,
            currency = excluded.currency,
            balance = excluded.balance,
            available_balance = excluded.available_balance,
            balance_date = excluded.balance_date,
            last_synced_at = excluded.last_synced_at
        """,
        (
            account.get("id"),
            org.get("name"),
            org.get("domain"),
            account.get("name"),
            account.get("currency"),
            _to_float(account.get("balance")),
            _to_float(account.get("available-balance")),
            _to_iso(account.get("balance-date")),
        ),
    )


def _upsert_transaction(
    conn: Conn,
    account_id: str,
    txn: dict[str, Any],
    auto_category: str | None,
) -> tuple[bool, bool]:
    """Insert or update one transaction. Returns (inserted, updated)."""

    txn_id = txn.get("id")
    if not txn_id:
        return (False, False)

    posted = _to_iso(txn.get("posted")) or _to_iso(txn.get("transacted_at")) or datetime.now(tz=timezone.utc).isoformat()
    transacted = _to_iso(txn.get("transacted_at"))
    amount = _to_float(txn.get("amount"))
    description = txn.get("description") or ""
    payee = txn.get("payee")
    memo = txn.get("memo")
    pending = 1 if txn.get("pending") else 0

    existing = conn.execute(
        "SELECT amount, description, payee, memo, pending, auto_category FROM transactions WHERE id = ?",
        (txn_id,),
    ).fetchone()

    if existing is None:
        conn.execute(
            """
            INSERT INTO transactions(
                id, account_id, posted_at, transacted_at, amount,
                description, payee, memo, pending, auto_category,
                first_seen_at, last_seen_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                txn_id,
                account_id,
                posted,
                transacted,
                amount,
                description,
                payee,
                memo,
                pending,
                auto_category,
            ),
        )
        return (True, False)

    changed = (
        existing["amount"] != amount
        or (existing["description"] or "") != description
        or (existing["payee"] or None) != payee
        or (existing["memo"] or None) != memo
        or int(existing["pending"]) != pending
        or (existing["auto_category"] or None) != (auto_category or None)
    )
    conn.execute(
        """
        UPDATE transactions
        SET account_id = ?,
            posted_at = ?,
            transacted_at = ?,
            amount = ?,
            description = ?,
            payee = ?,
            memo = ?,
            pending = ?,
            auto_category = COALESCE(?, auto_category),
            last_seen_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            account_id,
            posted,
            transacted,
            amount,
            description,
            payee,
            memo,
            pending,
            auto_category,
            txn_id,
        ),
    )
    return (False, changed)


def _store_raw(
    conn: Conn,
    run_id: int,
    account_id: str,
    transactions: Iterable[dict[str, Any]],
) -> None:
    rows = [
        (run_id, account_id, txn.get("id") or f"_no_id_{idx}", json.dumps(txn))
        for idx, txn in enumerate(transactions)
        if txn
    ]
    if not rows:
        return
    conn.executemany(
        """
        INSERT INTO transactions_raw(sync_run_id, account_id, transaction_id, payload)
        VALUES (?, ?, ?, ?)
        ON CONFLICT (sync_run_id, account_id, transaction_id) DO UPDATE SET
            payload = excluded.payload,
            captured_at = CURRENT_TIMESTAMP
        """,
        rows,
    )


def run_sync(config: AppConfig | None = None) -> SyncResult:
    cfg = config or load_config()
    if not cfg.has_access_url:
        raise SimpleFinError(
            "No SimpleFIN access URL is configured. Complete the Settings setup flow first."
        )

    initialize(cfg)
    payload: dict[str, Any] | None = None
    try:
        payload = fetch_accounts(cfg.access_url)
    except SimpleFinError as exc:
        with connect(cfg) as conn:
            run_id = _start_run(conn)
            _finish_run(
                conn,
                run_id,
                status="error",
                transactions_imported=0,
                transactions_updated=0,
                accounts_seen=0,
                error=str(exc),
            )
        return SyncResult(
            sync_run_id=run_id,
            status="error",
            transactions_imported=0,
            transactions_updated=0,
            accounts_seen=0,
            error=str(exc),
            simplefin_errors=[],
        )

    accounts = payload.get("accounts", []) or []
    simplefin_errors = [str(e) for e in (payload.get("errors") or [])]

    inserted = 0
    updated = 0

    with connect(cfg) as conn:
        run_id = _start_run(conn)
        rules = load_rules(conn)

        for account in accounts:
            if not account.get("id"):
                continue
            _upsert_account(conn, account)
            txns = account.get("transactions") or []
            _store_raw(conn, run_id, account["id"], txns)
            for txn in txns:
                auto_cat = classify(txn.get("description"), txn.get("payee"), rules)
                ins, upd = _upsert_transaction(conn, account["id"], txn, auto_cat)
                if ins:
                    inserted += 1
                elif upd:
                    updated += 1

        _finish_run(
            conn,
            run_id,
            status="ok" if not simplefin_errors else "ok_with_warnings",
            transactions_imported=inserted,
            transactions_updated=updated,
            accounts_seen=len(accounts),
            error="; ".join(simplefin_errors) if simplefin_errors else None,
        )

    return SyncResult(
        sync_run_id=run_id,
        status="ok" if not simplefin_errors else "ok_with_warnings",
        transactions_imported=inserted,
        transactions_updated=updated,
        accounts_seen=len(accounts),
        error=None,
        simplefin_errors=simplefin_errors,
    )


def reapply_rules(config: AppConfig | None = None) -> int:
    """Re-run the classifier against every existing transaction.

    Useful after the user creates or edits classification rules. Manual
    overrides remain untouched because they live in ``transaction_overrides``.
    Returns the number of rows whose ``auto_category`` value changed.
    """

    cfg = config or load_config()
    with connect(cfg) as conn:
        rules = load_rules(conn)
        rows = conn.execute(
            "SELECT id, description, payee, auto_category FROM transactions"
        ).fetchall()
        changed = 0
        for row in rows:
            new_cat = classify(row["description"], row["payee"], rules)
            if (row["auto_category"] or None) != (new_cat or None):
                conn.execute(
                    "UPDATE transactions SET auto_category = ? WHERE id = ?",
                    (new_cat, row["id"]),
                )
                changed += 1
        return changed
