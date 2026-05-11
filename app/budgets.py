"""Budget math: month aggregation, totals, and helpers shared by the UI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable

import pandas as pd

from .db import connect

UNCATEGORIZED_LABEL = "Uncategorized"


@dataclass(frozen=True)
class CategoryBudget:
    category: str
    month: str
    budgeted: float
    spent: float

    @property
    def remaining(self) -> float:
        return self.budgeted - self.spent


def current_month() -> str:
    return date.today().strftime("%Y-%m")


def list_months_with_data(limit: int = 24) -> list[str]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT substr(posted_at, 1, 7) AS month
            FROM transactions
            WHERE posted_at IS NOT NULL
            ORDER BY month DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    months = [r["month"] for r in rows]
    today = current_month()
    if today not in months:
        months.insert(0, today)
    return months


def transactions_dataframe(
    month: str | None = None,
    category: str | None = None,
    account_id: str | None = None,
    show_pending: bool = True,
) -> pd.DataFrame:
    sql = "SELECT * FROM v_transactions_classified WHERE 1 = 1"
    params: list = []
    if month:
        sql += " AND substr(posted_at, 1, 7) = ?"
        params.append(month)
    if category:
        if category == UNCATEGORIZED_LABEL:
            sql += " AND (category IS NULL OR category = '')"
        else:
            sql += " AND category = ?"
            params.append(category)
    if account_id:
        sql += " AND account_id = ?"
        params.append(account_id)
    if not show_pending:
        sql += " AND pending = 0"
    sql += " ORDER BY posted_at DESC, amount DESC"

    with connect() as conn:
        df = conn.query_df(sql, params)
    if not df.empty:
        df["posted_at"] = pd.to_datetime(df["posted_at"], utc=True, errors="coerce").dt.tz_convert("UTC")
    return df


def accounts_dataframe() -> pd.DataFrame:
    with connect() as conn:
        return conn.query_df(
            "SELECT * FROM v_account_effective_balance ORDER BY org_name, name"
        )


def categories_dataframe(include_archived: bool = False) -> pd.DataFrame:
    sql = "SELECT name, sort_order, is_income, is_archived FROM categories"
    if not include_archived:
        sql += " WHERE is_archived = 0"
    sql += " ORDER BY sort_order ASC, name ASC"
    with connect() as conn:
        return conn.query_df(sql)


def get_category_budgets(month: str) -> list[CategoryBudget]:
    sql = """
        SELECT c.name AS category,
               COALESCE(b.amount, 0) AS budgeted,
               COALESCE(spent.total, 0) AS spent
        FROM categories c
        LEFT JOIN budgets b
            ON b.category = c.name AND b.month = ?
        LEFT JOIN (
            SELECT category, SUM(amount) AS total
            FROM v_transactions_classified
            WHERE substr(posted_at, 1, 7) = ?
              AND category IS NOT NULL
            GROUP BY category
        ) spent ON spent.category = c.name
        WHERE c.is_archived = 0
        ORDER BY c.sort_order ASC, c.name ASC
    """
    with connect() as conn:
        rows = conn.execute(sql, (month, month)).fetchall()
    results: list[CategoryBudget] = []
    for row in rows:
        spent = float(row["spent"] or 0.0)
        spent_outflow = -spent if spent < 0 else 0.0
        results.append(
            CategoryBudget(
                category=row["category"],
                month=month,
                budgeted=float(row["budgeted"] or 0.0),
                spent=spent_outflow if row["category"].lower() != "income" else abs(spent),
            )
        )
    return results


def overview_totals(month: str) -> dict[str, float]:
    """Compute headline numbers for the Overview screen."""

    with connect() as conn:
        row = conn.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) AS inflow,
                COALESCE(SUM(CASE WHEN amount < 0 THEN -amount ELSE 0 END), 0) AS outflow
            FROM v_transactions_classified
            WHERE substr(posted_at, 1, 7) = ?
            """,
            (month,),
        ).fetchone()
        accounts = conn.execute(
            "SELECT COALESCE(SUM(balance), 0) AS total FROM v_account_effective_balance"
        ).fetchone()
        uncategorized = conn.execute(
            """
            SELECT COUNT(*) AS c
            FROM v_transactions_classified
            WHERE category IS NULL OR category = ''
            """
        ).fetchone()
        last_sync = conn.execute(
            "SELECT MAX(finished_at) AS ts FROM sync_runs WHERE status IN ('ok', 'ok_with_warnings')"
        ).fetchone()
    inflow = float(row["inflow"] or 0.0)
    outflow = float(row["outflow"] or 0.0)
    return {
        "inflow": inflow,
        "outflow": outflow,
        "net": inflow - outflow,
        "total_balance": float(accounts["total"] or 0.0),
        "uncategorized_count": int(uncategorized["c"] or 0),
        "last_sync": last_sync["ts"],
    }


def monthly_history(months_back: int = 6) -> pd.DataFrame:
    """Return one row per month with total spend and total income."""

    with connect() as conn:
        df = conn.query_df(
            """
            SELECT substr(posted_at, 1, 7) AS month,
                   SUM(CASE WHEN amount < 0 THEN -amount ELSE 0 END) AS spent,
                   SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) AS income
            FROM v_transactions_classified
            WHERE posted_at IS NOT NULL
            GROUP BY substr(posted_at, 1, 7)
            ORDER BY month DESC
            LIMIT ?
            """,
            (months_back,),
        )
    if not df.empty:
        df = df.sort_values("month")
    return df


def set_budget(category: str, month: str, amount: float) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO budgets(category, month, amount)
            VALUES (?, ?, ?)
            ON CONFLICT(category, month) DO UPDATE SET
                amount = excluded.amount,
                updated_at = CURRENT_TIMESTAMP
            """,
            (category, month, float(amount)),
        )


def set_transaction_category(transaction_id: str, category: str | None, note: str | None = None) -> None:
    if category is None and (note is None or note == ""):
        with connect() as conn:
            conn.execute(
                "DELETE FROM transaction_overrides WHERE transaction_id = ?",
                (transaction_id,),
            )
        return
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO transaction_overrides(transaction_id, category, note)
            VALUES (?, ?, ?)
            ON CONFLICT(transaction_id) DO UPDATE SET
                category = excluded.category,
                note = excluded.note,
                updated_at = CURRENT_TIMESTAMP
            """,
            (transaction_id, category, note),
        )


def upsert_category(name: str, *, sort_order: int | None = None, is_income: bool = False) -> None:
    with connect() as conn:
        existing = conn.execute(
            "SELECT sort_order FROM categories WHERE name = ?", (name,)
        ).fetchone()
        if existing is None:
            order = sort_order
            if order is None:
                max_row = conn.execute("SELECT COALESCE(MAX(sort_order), 0) AS m FROM categories").fetchone()
                order = int(max_row["m"]) + 1
            conn.execute(
                "INSERT INTO categories(name, sort_order, is_income) VALUES (?, ?, ?)",
                (name, order, 1 if is_income else 0),
            )
        else:
            conn.execute(
                "UPDATE categories SET is_income = ? WHERE name = ?",
                (1 if is_income else 0, name),
            )


def archive_category(name: str, archived: bool = True) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE categories SET is_archived = ? WHERE name = ?",
            (1 if archived else 0, name),
        )


def add_rule(pattern: str, category: str, match_field: str = "description", priority: int = 100) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO classification_rules(pattern, category, match_field, priority) VALUES (?, ?, ?, ?)",
            (pattern, category, match_field, priority),
        )


def delete_rule(rule_id: int) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM classification_rules WHERE id = ?", (rule_id,))


def rules_dataframe() -> pd.DataFrame:
    with connect() as conn:
        return conn.query_df(
            "SELECT id, pattern, category, match_field, priority, created_at FROM classification_rules ORDER BY priority ASC, id ASC"
        )


def sync_history(limit: int = 25) -> pd.DataFrame:
    with connect() as conn:
        return conn.query_df(
            "SELECT id, started_at, finished_at, status, transactions_imported, transactions_updated, accounts_seen, error FROM sync_runs ORDER BY id DESC LIMIT ?",
            (limit,),
        )


def set_account_balance_override(account_id: str, balance: float, note: str | None = None) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO account_balance_overrides(account_id, balance, note)
            VALUES (?, ?, ?)
            ON CONFLICT(account_id) DO UPDATE SET
                balance = excluded.balance,
                note = excluded.note,
                updated_at = CURRENT_TIMESTAMP
            """,
            (account_id, float(balance), note),
        )


def clear_account_balance_override(account_id: str) -> None:
    with connect() as conn:
        conn.execute(
            "DELETE FROM account_balance_overrides WHERE account_id = ?",
            (account_id,),
        )


def format_currency(value: float | None) -> str:
    if value is None:
        return ""
    return f"${value:,.2f}"


def filter_categories_for_select(categories: Iterable[str]) -> list[str]:
    return [c for c in categories if c]
