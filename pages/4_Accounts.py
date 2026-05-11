"""Accounts screen: balances, last-sync info, and manual balance overrides."""

from __future__ import annotations

import streamlit as st

from app.budgets import (
    accounts_dataframe,
    clear_account_balance_override,
    format_currency,
    set_account_balance_override,
)
from app.db import initialize
from app.ui import metric_card_html, render_markdown_html, time_ago


st.set_page_config(page_title="Accounts", layout="wide")
initialize()

st.title("Accounts")

st.caption(
    "Balances come from SimpleFIN and refresh on each sync. "
    "Use **Manual balance override** to display a corrected balance until the next sync."
)

accounts = accounts_dataframe()
if accounts.empty:
    st.info("No accounts have been synced yet. Use **Load Data** on the Overview page.")
    st.stop()

for _, row in accounts.iterrows():
    account_id = row["account_id"]
    display_name = (
        f"{(row.get('org_name') or '').strip()} {(row.get('name') or '').strip()}".strip()
        or account_id
    )
    synced_balance = float(row.get("balance") or 0.0)
    override = row.get("override_balance")
    has_override = override is not None and not (isinstance(override, float) and override != override)  # NaN check

    with st.container(border=True):
        top = st.columns([2, 1])
        with top[0]:
            sub_parts = []
            if row.get("available_balance") is not None:
                sub_parts.append(f"Available {format_currency(float(row['available_balance']))}")
            if row.get("last_synced_at"):
                sub_parts.append(f"Synced {time_ago(row['last_synced_at'])}")
            if row.get("currency"):
                sub_parts.append(str(row["currency"]))
            sub = " \u00b7 ".join(sub_parts)
            title = display_name + (" (manual override active)" if has_override else "")
            accent = "#dc2626" if synced_balance < 0 else "#111827"
            render_markdown_html(metric_card_html(title, format_currency(synced_balance), sub=sub, accent=accent))
        with top[1]:
            if has_override:
                st.caption(f"Override: {format_currency(float(override))}")
                if row.get("override_note"):
                    st.caption(f"Note: {row['override_note']}")

        with st.expander("Manual balance override", expanded=False):
            current = float(override) if has_override else synced_balance
            key_amt = f"acct_override_amt_{account_id}"
            key_note = f"acct_override_note_{account_id}"
            new_amount = st.number_input(
                "Display this balance instead",
                value=current,
                step=10.0,
                key=key_amt,
            )
            new_note = st.text_input(
                "Note (optional)",
                value=str(row.get("override_note") or ""),
                key=key_note,
            )
            bcols = st.columns([1, 1, 4])
            with bcols[0]:
                if st.button("Save override", key=f"save_override_{account_id}", type="primary"):
                    set_account_balance_override(account_id, float(new_amount), new_note or None)
                    st.rerun()
            with bcols[1]:
                if has_override and st.button("Clear", key=f"clear_override_{account_id}"):
                    clear_account_balance_override(account_id)
                    st.rerun()
