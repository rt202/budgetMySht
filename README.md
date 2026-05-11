# SimpleFIN Budget App

A personal budgeting app that imports Chase (checking + credit card) transactions
through [SimpleFIN Bridge](https://bridge.simplefin.org/), stores them in a
SQL database (SQLite locally, Postgres/Supabase in the cloud), and lets you
classify transactions, set monthly category budgets, and track remaining
balance.

The app has two deployment modes:

- **Local only**: SQLite + Streamlit on your Mac. Sync runs via a manual button
  or an optional macOS `launchd` job.
- **Cloud (recommended)**: Supabase Postgres + Streamlit Community Cloud +
  GitHub Actions daily sync. Phone-accessible from anywhere, no laptop needed.

## Requirements

- Python 3.11+
- A SimpleFIN Bridge account (`$15/year` or `$1.50/month`) with Chase linked

For cloud deployment (optional):

- Free Supabase account
- Free Streamlit Community Cloud account (uses your GitHub login)
- Free GitHub account with this repo pushed

## Quick start (local mode)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run streamlit_app.py
```

Open the URL Streamlit prints (usually `http://localhost:8501`) in Chrome or
Firefox. Safari may block plain HTTP localhost.

### Connect SimpleFIN

1. Log in to https://bridge.simplefin.org/ and link your Chase account.
2. Generate a **setup token** in the SimpleFIN dashboard.
3. Open **Settings** in the app and paste the setup token.
4. Click **Connect**. The app exchanges the one-time token for a long-lived
   access URL, stores it locally in `config.toml`, and runs the first sync.

The setup token can only be claimed once. After claiming, only the access URL
is stored. The access URL is treated as a secret; `config.toml` is gitignored.

## Daily workflow

- **Overview** shows current-month inflow, outflow, net, and per-category
  budget progress bars. A **Load Data** button triggers a fresh sync.
- **Transactions** lets you reclassify with an immediate-save dropdown; group
  by date or by category.
- **Categories** is where you add categories and classification rules.
- **Budget** uses card layout: pick a month, set the dollar amount per
  category, and see budgeted vs spent vs remaining at a glance.
- **Accounts** shows each account as a card with available balance, last sync
  time, and a manual balance override for cases where you want to display a
  corrected number.
- **Settings** holds connect/disconnect controls and stop-charge instructions.

## Cloud deployment

This is the recommended setup if you want phone access and a daily auto-sync
that works regardless of whether your Mac is awake.

```mermaid
flowchart TD
    githubActions[GitHub Actions cron] -->|daily| simplefin[SimpleFIN Bridge]
    simplefin --> pipeline[scripts/sync.py]
    pipeline --> supabase[Supabase Postgres]
    supabase --> streamlitCloud[Streamlit Community Cloud]
    streamlitCloud --> phone[Phone Browser]
    streamlitCloud --> desktop[Desktop Browser]
```

### 1. Push to GitHub

Create a private repo and push this directory.

### 2. Create the Supabase project

1. Sign up at https://supabase.com and create a new project (Free plan is fine).
2. Open the **SQL Editor**, paste the contents of
   [app/schema_pg.sql](app/schema_pg.sql), and run it once.
3. Open **Project Settings -> Database -> Connection string -> URI** and copy
   the connection string. It looks like
   `postgresql://postgres:PASSWORD@db.xxxxxxx.supabase.co:5432/postgres`.
4. (Optional) Insert your starting categories with the SQL editor so the cloud
   DB matches your local one. They will also be auto-seeded on first
   `initialize()` if the table is empty.

### 3. Move your SimpleFIN access URL out of `config.toml`

Run the app locally once to complete the setup-token flow. Then open the local
`config.toml`, copy the `access_url`, and treat it as a secret going forward.

### 4. Configure GitHub Actions

In the repo on GitHub, go to **Settings -> Secrets and variables -> Actions**
and add two repository secrets:

- `DATABASE_URL`: the Supabase connection string from step 2.
- `SIMPLEFIN_ACCESS_URL`: the SimpleFIN access URL from step 3.

The workflow in [.github/workflows/daily_sync.yml](.github/workflows/daily_sync.yml)
runs daily and can also be triggered manually from the Actions tab via
**Run workflow**. It runs entirely on GitHub's servers; your laptop does not
need to be awake.

### 5. Deploy to Streamlit Community Cloud

1. Sign in at https://share.streamlit.io/ with your GitHub account.
2. Click **New app**, pick this repo, branch `main`, and the entry point
   `streamlit_app.py`.
3. In **Advanced settings -> Secrets**, paste the same values as TOML:

   ```toml
   DATABASE_URL = "postgresql://postgres:...@db.xxxxxxx.supabase.co:5432/postgres"
   SIMPLEFIN_ACCESS_URL = "https://user:pass@beta-bridge.simplefin.org/.../accounts"
   ```

4. Deploy. The app will read both secrets via `st.secrets` and use the
   Supabase DB automatically.

You now have:

- A daily auto-sync running on GitHub's servers.
- A Streamlit app accessible from your phone at the URL Streamlit Cloud gives
  you (and from your laptop, of course).
- All data stored in Supabase, so you can also query it directly with `psql`,
  Supabase Studio, or any Postgres client.

## Optional local automation: macOS launchd

If you want the local sync to also run automatically (for example, when you
are using SQLite-only mode):

```bash
PYTHON_BIN="$(pwd)/.venv/bin/python" bash scripts/install_launchd.sh
```

This installs a `launchd` agent that runs `python -m scripts.sync` once per day
at 07:00 local time, **only when the Mac is awake**. Remove it with:

```bash
bash scripts/uninstall_launchd.sh
```

For reliable daily sync that does not depend on your laptop, use the GitHub
Actions workflow instead.

## Stopping charges and disconnecting

- **Cancel the SimpleFIN Bridge subscription** at
  https://bridge.simplefin.org/ to stop the recurring charge.
- **Revoke this app's access** without canceling SimpleFIN by clicking
  **Disconnect SimpleFIN** in the in-app Settings page, then disabling the
  access token in the SimpleFIN Bridge dashboard. Also delete the GitHub
  Actions secret `SIMPLEFIN_ACCESS_URL` and the Streamlit Cloud secret.
- **Stop only the daily background sync (cloud)**: disable the workflow at
  GitHub repo **Actions -> Daily SimpleFIN Sync -> ... -> Disable workflow**.
- **Stop only the daily background sync (local launchd)**: run
  `bash scripts/uninstall_launchd.sh`.

For full cost discussion (Plaid vs Teller vs SimpleFIN), see
[AUTOMATED_BANK_SYNC_COSTS.md](AUTOMATED_BANK_SYNC_COSTS.md).

## Data model

Tables (same names in SQLite and Postgres):

| Table | Purpose |
| --- | --- |
| `accounts` | SimpleFIN account records (checking, credit card, etc.) |
| `account_balance_overrides` | Optional manual balance display value |
| `transactions` | Normalized transactions, unique by SimpleFIN id |
| `transactions_raw` | Original SimpleFIN payloads for every sync run |
| `categories` | Editable category list |
| `transaction_overrides` | Manual category + note edits (survive re-imports) |
| `classification_rules` | Substring rules that suggest a category |
| `budgets` | Monthly category budget amounts |
| `sync_runs` | Audit log: timestamps, counts, errors |
| `v_transactions_classified` | View joining transactions to effective category |
| `v_account_effective_balance` | View applying manual balance overrides |

Query directly with `sqlite3` (local) or any Postgres client (cloud).

## Project layout

```
.
├── streamlit_app.py            Overview page
├── pages/                      Streamlit multipage screens
│   ├── 1_Transactions.py
│   ├── 2_Categories.py
│   ├── 3_Budget.py
│   ├── 4_Accounts.py
│   └── 5_Settings.py
├── app/                        Backend modules
│   ├── config.py               Config + env/secret resolution
│   ├── db.py                   Dual-backend Conn wrapper
│   ├── schema.sql              SQLite schema
│   ├── schema_pg.sql           Postgres schema for Supabase
│   ├── simplefin.py            SimpleFIN client
│   ├── ingestion.py            Sync pipeline
│   ├── classifier.py           Rule-based auto-categorization
│   ├── budgets.py              UI-facing queries
│   └── ui.py                   Shared HTML primitives
├── scripts/
│   ├── sync.py                 Headless sync (used by launchd and GH Actions)
│   ├── install_launchd.sh
│   ├── uninstall_launchd.sh
│   └── com.user.simplefin-sync.plist.template
├── .github/workflows/daily_sync.yml
├── AUTOMATED_BANK_SYNC_COSTS.md
├── requirements.txt
├── config.example.toml
└── README.md
```
