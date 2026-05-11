"""Budget screen: set per-category monthly amounts with inline editing."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app.budgets import (
    current_month,
    format_currency,
    get_category_budgets,
    list_months_with_data,
    monthly_history,
    set_budget,
)
from app.db import initialize
from app.ui import progress_bar_html, render_markdown_html


st.set_page_config(page_title="Budget", layout="wide")
initialize()

st.title("Budget")

months = list_months_with_data()
default_month = current_month()
month = st.selectbox(
    "Month",
    options=months,
    index=months.index(default_month) if default_month in months else 0,
)

budgets = get_category_budgets(month)

total_budgeted = sum(b.budgeted for b in budgets)
total_spent = sum(b.spent for b in budgets if b.category.lower() != "income")
total_remaining = total_budgeted - total_spent

summary = st.columns(3)
summary[0].metric("Budgeted", format_currency(total_budgeted))
summary[1].metric("Spent", format_currency(total_spent))
summary[2].metric(
    "Remaining",
    format_currency(total_remaining),
    delta=None if total_budgeted == 0 else f"{(total_remaining/total_budgeted*100):.0f}% left" if total_budgeted else None,
)

st.divider()

if not budgets:
    st.info("No categories yet. Add some on the Categories page.")
else:
    for b in budgets:
        with st.container(border=True):
            cols = st.columns([3, 1])
            with cols[0]:
                sub = (
                    f"{format_currency(b.remaining)} remaining"
                    if b.budgeted > 0
                    else "no budget set"
                )
                render_markdown_html(progress_bar_html(b.category, b.spent, b.budgeted, sub_label=sub))
            with cols[1]:
                new_amount = st.number_input(
                    "Monthly budget",
                    min_value=0.0,
                    step=10.0,
                    value=float(b.budgeted),
                    key=f"budget_{month}_{b.category}",
                    label_visibility="collapsed",
                )
                if abs(new_amount - b.budgeted) > 0.005:
                    if st.button("Save", key=f"save_{month}_{b.category}"):
                        set_budget(b.category, month, float(new_amount))
                        st.rerun()

st.divider()
st.subheader("Spending history (last 6 months)")
history = monthly_history(6)
if history.empty:
    st.caption("No history yet. Sync some transactions first.")
else:
    chart_df = history.copy().set_index("month")
    st.bar_chart(chart_df[["spent", "income"]])
    table = chart_df.copy()
    table["spent"] = table["spent"].apply(format_currency)
    table["income"] = table["income"].apply(format_currency)
    st.dataframe(table, width="stretch")
