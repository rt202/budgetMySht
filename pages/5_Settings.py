"""Settings: connect/disconnect SimpleFIN, sync history, and disclosures."""

from __future__ import annotations

import streamlit as st

from app.budgets import sync_history
from app.config import clear_access_url, load_config, save_access_url
from app.db import initialize
from app.ingestion import run_sync
from app.simplefin import SimpleFinError, claim_access_url


st.set_page_config(page_title="Settings", layout="wide")
initialize()

st.title("Settings")

cfg = load_config()

st.subheader("SimpleFIN connection")
if cfg.has_access_url:
    st.success("SimpleFIN is connected.")
    st.caption("Your access URL is stored locally in `config.toml` and never leaves this machine.")
    if st.button("Disconnect SimpleFIN", type="secondary"):
        clear_access_url()
        st.warning(
            "Local access URL cleared. To fully revoke access, also disable this app's "
            "access token at https://bridge.simplefin.org/."
        )
        st.rerun()
else:
    st.info(
        "Paste a SimpleFIN setup token below. Generate one at "
        "https://bridge.simplefin.org/ after you have linked your bank."
    )
    with st.form("connect_simplefin"):
        setup_token = st.text_area("Setup token", height=120, placeholder="Paste setup token here")
        submitted = st.form_submit_button("Connect")
        if submitted and setup_token.strip():
            try:
                access_url = claim_access_url(setup_token.strip())
                save_access_url(access_url)
            except SimpleFinError as exc:
                st.error(f"Could not claim setup token: {exc}")
            else:
                st.success("Connected. Running initial sync...")
                try:
                    result = run_sync(load_config())
                    st.info(
                        f"Imported {result.transactions_imported} transactions across "
                        f"{result.accounts_seen} account(s)."
                    )
                except SimpleFinError as exc:
                    st.warning(f"Connected, but initial sync failed: {exc}")
                st.rerun()

st.divider()

st.subheader("Sync history")
history = sync_history(limit=25)
if history.empty:
    st.write("No sync runs yet.")
else:
    st.dataframe(history, width="stretch", hide_index=True)

st.divider()

st.subheader("Stopping charges and disconnecting")
st.markdown(
    """
- The SimpleFIN Bridge subscription is **$15/year or $1.50/month**.
- To stop being charged for SimpleFIN Bridge, cancel the subscription at
  [https://bridge.simplefin.org/](https://bridge.simplefin.org/) using the account you signed up with.
- To stop **this app** from accessing data without canceling the subscription,
  click **Disconnect SimpleFIN** above and disable the access token in SimpleFIN Bridge.
- For full cost details and exit steps, see `AUTOMATED_BANK_SYNC_COSTS.md` in the project root.
    """
)
