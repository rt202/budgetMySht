"""Shared UI primitives used across Streamlit pages.

The aim is a card-and-progress-bar UI rather than table-heavy screens. All
helpers are lightweight Streamlit/HTML so we do not pull in extra widget libs.
"""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape

import streamlit as st

from .budgets import format_currency


def time_ago(timestamp: str | None) -> str:
    """Human-friendly relative-time string. Accepts ISO-ish strings."""
    if not timestamp:
        return "never"
    try:
        ts = datetime.fromisoformat(str(timestamp).replace(" ", "T").split(".")[0])
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
    except ValueError:
        return str(timestamp)
    delta = datetime.now(tz=timezone.utc) - ts
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        m = seconds // 60
        return f"{m} minute{'s' if m != 1 else ''} ago"
    if seconds < 86400:
        h = seconds // 3600
        return f"{h} hour{'s' if h != 1 else ''} ago"
    days = seconds // 86400
    return f"{days} day{'s' if days != 1 else ''} ago"


def status_color(spent: float, budgeted: float) -> str:
    """Pick a color for a budget progress bar based on usage ratio."""
    if budgeted <= 0:
        return "#6c757d"  # gray when no budget set
    ratio = spent / budgeted if budgeted else 0
    if ratio < 0.7:
        return "#16a34a"  # green
    if ratio < 1.0:
        return "#f59e0b"  # amber
    return "#dc2626"  # red


def progress_bar_html(label: str, spent: float, budgeted: float, *, sub_label: str = "") -> str:
    """Render a styled labeled progress bar via raw HTML/CSS."""
    safe_label = escape(label)
    safe_sub = escape(sub_label) if sub_label else ""
    color = status_color(spent, budgeted)
    pct = 0 if budgeted <= 0 else min(int(round(spent / budgeted * 100)), 100)
    width = "100%" if budgeted > 0 and spent >= budgeted else f"{pct}%"
    if budgeted <= 0:
        right = format_currency(spent) + " spent"
    else:
        right = f"{format_currency(spent)} / {format_currency(budgeted)}"
    return f"""
    <div style="margin-bottom: 0.75rem;">
      <div style="display:flex; justify-content:space-between; font-size: 0.95rem; margin-bottom:0.25rem;">
        <span><strong>{safe_label}</strong>{' &middot; <span style="color:#6b7280">' + safe_sub + '</span>' if safe_sub else ''}</span>
        <span style="color:#374151">{right}</span>
      </div>
      <div style="background:#e5e7eb; border-radius:6px; height:10px; overflow:hidden;">
        <div style="background:{color}; width:{width}; height:100%;"></div>
      </div>
    </div>
    """


def metric_card_html(title: str, value: str, *, sub: str = "", accent: str = "#111827") -> str:
    return f"""
    <div style="border:1px solid #e5e7eb; border-radius:10px; padding:1rem 1.25rem; background:#ffffff;">
      <div style="color:#6b7280; font-size:0.85rem; text-transform:uppercase; letter-spacing:0.04em;">{escape(title)}</div>
      <div style="color:{accent}; font-size:1.6rem; font-weight:600; margin-top:0.25rem;">{escape(value)}</div>
      {f'<div style="color:#6b7280; font-size:0.85rem; margin-top:0.25rem;">{escape(sub)}</div>' if sub else ''}
    </div>
    """


def category_badge_html(category: str | None) -> str:
    if not category:
        return '<span style="background:#fef3c7; color:#92400e; padding:2px 8px; border-radius:9999px; font-size:0.75rem;">uncategorized</span>'
    return f'<span style="background:#e0e7ff; color:#3730a3; padding:2px 8px; border-radius:9999px; font-size:0.75rem;">{escape(category)}</span>'


def amount_span_html(amount: float) -> str:
    color = "#16a34a" if amount > 0 else ("#dc2626" if amount < 0 else "#6b7280")
    return f'<span style="color:{color}; font-weight:600;">{escape(format_currency(amount))}</span>'


def render_markdown_html(html: str) -> None:
    st.markdown(html, unsafe_allow_html=True)
