"""Categories and classification rules."""

from __future__ import annotations

import streamlit as st

from app.budgets import (
    add_rule,
    archive_category,
    categories_dataframe,
    delete_rule,
    rules_dataframe,
    upsert_category,
)
from app.db import initialize
from app.ingestion import reapply_rules


st.set_page_config(page_title="Categories", layout="wide")
initialize()

st.title("Categories")

categories = categories_dataframe(include_archived=True)
st.dataframe(categories, width="stretch", hide_index=True)

st.subheader("Add or update a category")
with st.form("add_category"):
    new_name = st.text_input("Name", "")
    is_income = st.checkbox("Income category", value=False)
    submitted = st.form_submit_button("Save")
    if submitted and new_name.strip():
        upsert_category(new_name.strip(), is_income=is_income)
        st.success(f"Saved {new_name.strip()}")
        st.rerun()

st.subheader("Archive a category")
active = categories[categories["is_archived"] == 0]["name"].tolist()
archived = categories[categories["is_archived"] == 1]["name"].tolist()
col1, col2 = st.columns(2)
with col1:
    to_archive = st.selectbox("Archive", options=["(select)"] + active, index=0)
    if st.button("Archive selected") and to_archive != "(select)":
        archive_category(to_archive, archived=True)
        st.rerun()
with col2:
    to_unarchive = st.selectbox("Unarchive", options=["(select)"] + archived, index=0)
    if st.button("Unarchive selected") and to_unarchive != "(select)":
        archive_category(to_unarchive, archived=False)
        st.rerun()

st.divider()

st.title("Classification rules")
st.caption(
    "Rules suggest a category automatically when a transaction's description or "
    "payee contains the pattern. Manual edits in the Transactions page always win."
)

rules = rules_dataframe()
if rules.empty:
    st.write("No rules yet.")
else:
    st.dataframe(rules, width="stretch", hide_index=True)
    delete_id = st.number_input("Delete rule id", min_value=0, step=1, value=0)
    if st.button("Delete rule") and delete_id:
        delete_rule(int(delete_id))
        st.rerun()

st.subheader("Add a rule")
with st.form("add_rule"):
    pattern = st.text_input("Pattern (substring, case-insensitive)", "")
    available_categories = categories_dataframe()["name"].tolist()
    rule_category = st.selectbox("Category", options=available_categories)
    match_field = st.selectbox("Match field", options=["description", "payee"], index=0)
    priority = st.number_input("Priority (lower = checked first)", min_value=0, value=100)
    submitted = st.form_submit_button("Save rule")
    if submitted and pattern.strip() and rule_category:
        add_rule(pattern.strip(), rule_category, match_field=match_field, priority=int(priority))
        st.success("Rule added.")
        st.rerun()

if st.button("Reapply rules to all transactions"):
    changed = reapply_rules()
    st.success(f"Updated suggested category on {changed} transaction(s).")
