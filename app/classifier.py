"""Rule-based auto-categorization.

Rules match against a transaction's description or payee using a simple
substring contains check (case-insensitive). Manual overrides in
``transaction_overrides`` always win, so the auto category is treated as a
suggestion that the UI can show until the user accepts it.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    pattern: str
    category: str
    match_field: str


def load_rules(conn: sqlite3.Connection) -> list[Rule]:
    rows = conn.execute(
        "SELECT pattern, category, match_field FROM classification_rules ORDER BY priority ASC, id ASC"
    ).fetchall()
    return [Rule(pattern=r["pattern"], category=r["category"], match_field=r["match_field"]) for r in rows]


def classify(description: str | None, payee: str | None, rules: list[Rule]) -> str | None:
    description = (description or "").lower()
    payee = (payee or "").lower()
    for rule in rules:
        haystack = payee if rule.match_field == "payee" else description
        if rule.pattern.strip().lower() in haystack:
            return rule.category
    return None
