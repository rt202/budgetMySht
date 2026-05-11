"""Streamlit entrypoint for the SimpleFIN Budget App.

Run with:

    streamlit run streamlit_app.py
"""

from __future__ import annotations

import streamlit as st

from app.budgets import (
    accounts_dataframe,
    current_month,
    format_currency,
    get_category_budgets,
    overview_totals,
)
from app.config import load_config
from app.db import initialize
from app.ingestion import SyncResult, run_sync
from app.simplefin import SimpleFinError
from app.ui import (
    metric_card_html,
    progress_bar_html,
    render_markdown_html,
    time_ago,
)


st.set_page_config(page_title="Budget", page_icon=":bar_chart:", layout="wide")


def _ensure_initialized() -> None:
    cfg = load_config()
    initialize(cfg)
    st.session_state.setdefault("config", cfg)


def _sync_now() -> None:
    cfg = load_config()
    if not cfg.has_access_url:
        st.warning("Connect SimpleFIN on the Settings page before loading data.")
        return
    try:
        with st.spinner("Fetching from SimpleFIN..."):
            result: SyncResult = run_sync(cfg)
    except SimpleFinError as exc:
        st.error(f"Sync failed: {exc}")
        return
    if result.status == "ok":
        st.toast(
            f"Synced: {result.transactions_imported} new, {result.transactions_updated} updated",
            icon=":material/check_circle:",
        )
    else:
        st.warning(
            f"Sync finished with warnings. {result.transactions_imported} new, "
            f"{result.transactions_updated} updated. {'; '.join(result.simplefin_errors) or result.error}"
        )


_ensure_initialized()

cfg = load_config()
month = current_month()
totals = overview_totals(month)

st.title("Overview")

if not cfg.has_access_url:
    st.info(
        "No SimpleFIN connection yet. Open **Settings** in the sidebar to paste a setup token."
    )

top = st.columns([1, 1, 1, 1, 2])
with top[0]:
    if st.button("Load Data", type="primary", width="stretch"):
        _sync_now()
        st.rerun()
with top[4]:
    st.caption(f"Last sync: {time_ago(totals['last_sync'])}")

st.markdown(" ")

mcols = st.columns(4)
with mcols[0]:
    render_markdown_html(
        metric_card_html("Total balance", format_currency(totals["total_balance"]), sub="across all accounts")
    )
with mcols[1]:
    render_markdown_html(
        metric_card_html("Net this month", format_currency(totals["net"]), sub=month, accent="#16a34a" if totals["net"] >= 0 else "#dc2626")
    )
with mcols[2]:
    render_markdown_html(
        metric_card_html("Inflow", format_currency(totals["inflow"]), sub=month, accent="#16a34a")
    )
with mcols[3]:
    render_markdown_html(
        metric_card_html("Outflow", format_currency(totals["outflow"]), sub=month, accent="#dc2626")
    )

if totals["uncategorized_count"]:
    st.warning(
        f"{totals['uncategorized_count']} transaction(s) without a category. "
        "Open Transactions to review."
    )

st.markdown("### Budgets this month")
budgets = [b for b in get_category_budgets(month) if b.budgeted > 0 or b.spent > 0]
if not budgets:
    st.caption("Set a monthly budget on the Budget page to see progress here.")
else:
    bcols = st.columns(2)
    for idx, b in enumerate(budgets):
        with bcols[idx % 2]:
            sub = f"{format_currency(b.remaining)} left" if b.budgeted > 0 else "no budget set"
            render_markdown_html(progress_bar_html(b.category, b.spent, b.budgeted, sub_label=sub))

st.markdown("### Accounts")
accounts = accounts_dataframe()
if accounts.empty:
    st.caption("No accounts synced yet.")
else:
    acols = st.columns(min(len(accounts), 3) or 1)
    for idx, row in accounts.iterrows():
        with acols[idx % len(acols)]:
            display_name = f"{row.get('org_name') or ''} {row.get('name') or ''}".strip() or row["account_id"]
            balance = float(row.get("balance") or 0.0)
            accent = "#dc2626" if balance < 0 else "#111827"
            sub_parts = []
            if row.get("available_balance") is not None:
                sub_parts.append(f"Available {format_currency(float(row['available_balance']))}")
            if row.get("last_synced_at"):
                sub_parts.append(f"Synced {time_ago(row['last_synced_at'])}")
            override_note = ""
            if row.get("override_balance") is not None:
                override_note = " (manual override)"
            render_markdown_html(
                metric_card_html(
                    display_name + override_note,
                    format_currency(balance),
                    sub=" \u00b7 ".join(sub_parts),
                    accent=accent,
                )
            )
