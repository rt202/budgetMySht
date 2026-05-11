"""Transactions screen: review, reclassify, and annotate transactions."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app.budgets import (
    UNCATEGORIZED_LABEL,
    accounts_dataframe,
    categories_dataframe,
    current_month,
    format_currency,
    list_months_with_data,
    set_transaction_category,
    transactions_dataframe,
)
from app.db import initialize
from app.ui import amount_span_html, category_badge_html, render_markdown_html


st.set_page_config(page_title="Transactions", layout="wide")
initialize()

st.title("Transactions")


def _save_category(txn_id: str, key_cat: str, key_note: str) -> None:
    new_cat = st.session_state.get(key_cat) or None
    new_note = (st.session_state.get(key_note) or "").strip() or None
    if new_cat == "(none)":
        new_cat = None
    set_transaction_category(txn_id, new_cat, new_note)


months = list_months_with_data()
categories = categories_dataframe()
category_names = categories["name"].tolist()
category_options = ["(none)"] + category_names
accounts = accounts_dataframe()

with st.sidebar:
    st.header("Filters")
    month_options = ["(all)"] + months
    default_month = current_month()
    default_idx = month_options.index(default_month) if default_month in month_options else 0
    month = st.selectbox("Month", options=month_options, index=default_idx)
    category_filter_options = ["(all)", UNCATEGORIZED_LABEL] + category_names
    category = st.selectbox("Category", options=category_filter_options, index=0)

    if not accounts.empty:
        account_lookup = {
            row["account_id"]: f"{(row.get('org_name') or '').strip()} {(row.get('name') or '').strip()}".strip()
            or row["account_id"]
            for _, row in accounts.iterrows()
        }
        account_options = ["(all)"] + list(account_lookup.keys())
        account_id = st.selectbox(
            "Account",
            options=account_options,
            format_func=lambda v: "(all)" if v == "(all)" else account_lookup.get(v, v),
        )
    else:
        account_id = "(all)"

    show_pending = st.checkbox("Show pending", value=True)
    group_by = st.radio("Group by", options=["Date", "Category"], horizontal=True)

df = transactions_dataframe(
    month=None if month == "(all)" else month,
    category=None if category == "(all)" else category,
    account_id=None if account_id == "(all)" else account_id,
    show_pending=show_pending,
)

uncategorized_total = transactions_dataframe(
    month=None if month == "(all)" else month,
    category=UNCATEGORIZED_LABEL,
)
if not uncategorized_total.empty:
    st.warning(
        f"{len(uncategorized_total)} transaction(s) without a category"
        + (f" in {month}." if month != "(all)" else ".")
        + " Set the Category filter to 'Uncategorized' to focus on them."
    )

if df.empty:
    st.info("No transactions match the current filters. Use **Load Data** on the Overview page to sync.")
    st.stop()

st.caption(f"{len(df)} transaction(s)")


def _render_row(row: pd.Series) -> None:
    txn_id = row["transaction_id"]
    posted = pd.to_datetime(row["posted_at"], utc=True).strftime("%a %b %d")
    amount = float(row["amount"])
    desc = (row.get("description") or "").strip() or "(no description)"
    payee = (row.get("payee") or "").strip()
    account = (row.get("account_name") or "").strip()
    pending = bool(row.get("pending"))
    current_cat = row.get("category") or ""
    current_note = row.get("note") or ""

    with st.container(border=True):
        cols = st.columns([3, 1, 2, 2])
        with cols[0]:
            render_markdown_html(
                f"""
                <div>
                  <div style="font-weight:600; font-size:0.95rem;">{desc}</div>
                  <div style="color:#6b7280; font-size:0.8rem;">
                    {posted} &middot; {account or 'account'}{(' &middot; ' + payee) if payee else ''}
                    {' &middot; <span style=\"color:#b45309\">pending</span>' if pending else ''}
                  </div>
                </div>
                """
            )
        with cols[1]:
            render_markdown_html(
                f'<div style="text-align:right; padding-top:0.25rem;">{amount_span_html(amount)}</div>'
            )
        with cols[2]:
            key_cat = f"txn_cat_{txn_id}"
            if key_cat not in st.session_state:
                st.session_state[key_cat] = current_cat if current_cat in category_names else "(none)"
            key_note = f"txn_note_{txn_id}"
            st.selectbox(
                "Category",
                options=category_options,
                key=key_cat,
                label_visibility="collapsed",
                on_change=_save_category,
                args=(txn_id, key_cat, key_note),
            )
        with cols[3]:
            key_note = f"txn_note_{txn_id}"
            if key_note not in st.session_state:
                st.session_state[key_note] = current_note
            key_cat = f"txn_cat_{txn_id}"
            st.text_input(
                "Note",
                key=key_note,
                placeholder="note",
                label_visibility="collapsed",
                on_change=_save_category,
                args=(txn_id, key_cat, key_note),
            )


if group_by == "Date":
    for _, row in df.iterrows():
        _render_row(row)
else:
    df_sorted = df.copy()
    df_sorted["_cat"] = df_sorted["category"].fillna(UNCATEGORIZED_LABEL).replace("", UNCATEGORIZED_LABEL)
    for cat, group in df_sorted.groupby("_cat", sort=True):
        subtotal = float(group["amount"].sum())
        render_markdown_html(
            f'<div style="margin-top:1rem; padding:0.5rem 0.75rem; background:#f3f4f6; border-radius:8px;">'
            f'<strong>{cat}</strong> &middot; <span style="color:#374151">{format_currency(subtotal)}</span>'
            f' &middot; <span style="color:#6b7280">{len(group)} transaction(s)</span></div>'
        )
        for _, row in group.iterrows():
            _render_row(row)
