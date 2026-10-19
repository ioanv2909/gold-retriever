# Technical Documentation for the Application

The documentation below is based **only on the code present in the chat**.  
Where something cannot be confirmed from the code, I state **“nu reiese din cod”**.

## 1. Overview

This application is a **Streamlit-based local portfolio analyzer** for a Trading 212 account.

In short, it:

- loads cached portfolio data, dividends, ratings, and market context;
- shows portfolio summary metrics;
- displays a sortable/filterable table of open positions;
- calculates returns, dividend yield, total return, and comparison vs. S&P 500;
- shows a detail view for a selected position;
- can refresh core portfolio data immediately and refresh dividends/ratings in the background;
- persists API credentials and refresh interval in a config file.

## 2. File-by-file documentation

## `app.py`

### Role
This is the **main Streamlit entry point** of the application. It builds the UI, loads cached data, triggers refresh actions, computes portfolio metrics, and routes to the detail view.

### Important imports
It imports:

- `streamlit as st` — UI and app state
- `requests` — imported but **nu reiese din cod** if it is used in this file
- `pandas as pd` — tabular transformations
- `numpy as np` — imported but **nu reiese din cod** if it is used in this file
- `base64` — imported but **nu reiese din cod** if it is used in this file
- `os` — filesystem checks and directory creation
- `json` — imported but **nu reiese din cod** if it is used in this file
- `time` — sleep during background refresh polling
- `threading` — imported but **nu reiese din cod** if it is used in this file
- `tempfile` — imported but **nu reiese din cod** if it is used in this file
- `datetime` from `datetime` — timestamp formatting
- `quote` from `urllib.parse` — building clickable link targets
- `plotly.graph_objects as go` — portfolio history chart
- `plotly.express as px` — imported but **nu reiese din cod** if it is used in this file
- `streamlit.components.v1 as components` — imported but **nu reiese din cod** if it is used in this file

Internal imports:

- from `core`
  - `CONFIG_FILE`
  - `RECOMMENDATION_LABELS`
  - `check_loss_to_profit_alerts`
  - `days_held_from_iso`
  - `dismiss_alert`
  - `load_config`
  - `record_portfolio_point`
  - `save_config`
  - `load_portfolio_history`
  - `record_portfolio_point` is imported twice
- from `t212_api`
  - `fetch_account_currency`
  - `fetch_and_cache_core`
  - `fetch_fx_rate`
  - `load_cached_dividends`
  - `load_cached_ratings`
  - `load_cached_snapshot`
- from `yahoo`
  - `fetch_benchmark_return`
  - `fetch_yahoo_peg_ratio`
  - `resolve_yahoo_symbol`
- from `background`
  - `load_dividends_status`
  - `load_market_context_cache`
  - `load_quality_cache`
  - `load_ratings_status`
  - `start_background_scheduler`
  - `start_dividends_fetch_background`
  - `start_quality_fetch_background`
  - `start_ratings_fetch_background`
- from `detail_view`
  - `render_detail_view`
  - `scroll_page_to_top`

### Important constants / variables
There are no application-level constants defined in this file besides `YFINANCE_AVAILABLE`:

- `YFINANCE_AVAILABLE` — `True` if `yfinance` imports successfully, otherwise `False`.  
  It is defined but **nu reiese din cod** that it is used later in this file.

### Main flow
The file:

1. sets Streamlit page config;
2. creates `data/` directory if missing;
3. loads configuration;
4. renders sidebar controls for API key/secret and refresh interval;
5. starts background scheduler;
6. renders either the main portfolio view or the detail view depending on session state.

### Functions

#### `render_main_view()`
This is the main page renderer.

It:
- checks whether the page is in “detail loading” mode based on query params;
- displays a top title;
- loads cached snapshot and shows “loss-to-profit” alerts if any;
- renders update buttons for:
  - core portfolio data
  - dividends
  - ratings / quality data
- reloads snapshot after update actions;
- shows portfolio timestamps and error messages if present;
- computes portfolio metrics and derived columns;
- merges instrument metadata if available;
- converts GBX to GBP for display;
- fetches account currency and FX rates;
- computes dividend-derived metrics;
- loads ratings and quality caches;
- shows summary metrics and portfolio history chart;
- shows cash summary and update status captions;
- prepares a detailed positions table;
- allows filtering by recommendation;
- builds clickable links to the detail view;
- renders the table;
- polls background jobs and reruns while they are active.

No other functions are defined in this file.

## `Dockerfile`

### Role
Builds a container image for running the Streamlit app.

### Content and purpose
- Uses `python:3.10-slim`
- Sets `/app` as working directory
- Copies `requirements.txt`
- Installs dependencies with `pip`
- Copies the rest of the project
- Exposes port `8501`
- Starts Streamlit with:
  - `streamlit run app.py --server.port=8501 --server.address=0.0.0.0 --server.runOnSave=true`

## 3. Sources de date

## Trading 212

### Used via
The code does not show the implementation of `t212_api`, so the exact HTTP endpoints are **nu reiese din cod**.

What is observable from `app.py`:

- `fetch_and_cache_core(api_key_id, api_secret)`  
  Refreshes core portfolio data.
- `fetch_account_currency(api_key_id, api_secret)`  
  Retrieves the account currency.
- `fetch_fx_rate(ccy, account_currency)`  
  Retrieves an FX conversion rate.
- `load_cached_snapshot()`  
  Reads cached portfolio snapshot.
- `load_cached_dividends()`  
  Reads cached dividend data.
- `load_cached_ratings()`  
  Reads cached ratings data.

### Data brought in
From the names and downstream usage, the application expects these data types:

- portfolio snapshot with:
  - `fetched_at`
  - `positions`
  - `cash`
  - `instruments`
  - `errors`
- dividend cache with:
  - per-ticker `total`
  - `fetched_at`
  - `error`
- ratings cache with:
  - per-ticker recommendation values
  - `fetched_at`
- account currency
- FX rates between instrument currency and account currency

### Frequency
- Core data is refreshed:
  - manually via the “Actualizează acum” button
  - automatically via `start_background_scheduler()`
- Dividends and ratings are refreshed:
  - manually via dedicated background buttons
  - also through background processes
- The exact schedule for automatic refresh is **nu reiese din cod** beyond the sidebar value `interval_minutes` and the background scheduler call.

### Cache location
The exact cache file paths are **nu reiese din cod** in `app.py`; they are handled inside `t212_api`, `core`, or `background`.

## Yahoo Finance / `yfinance`

### Used via
Imports in `app.py`:

- `fetch_benchmark_return`
- `fetch_yahoo_peg_ratio`
- `resolve_yahoo_symbol`

Also `yfinance as yf` is conditionally imported.

### What is used in this file
In `app.py` itself, these Yahoo-related imports are present, but **nu reiese din cod** that they are directly called in this file.

However, the UI clearly depends on Yahoo-derived data through:

- `load_market_context_cache()`
- columns:
  - `sp500_return_%`
  - `peg_ratio_display`
  - `alpha_%`

So Yahoo/market context is likely handled in background code or helper modules, but the implementation details are **nu reiese din cod**.

### Data brought in
From the UI usage:
- S&P 500 return over the position holding period
- PEG ratio

### Frequency
The refresh cadence is **nu reiese din cod**.
The app simply reads from the market context cache.

### Cache location
`load_market_context_cache()` suggests a cache managed by `background`, but the file path is **nu reiese din cod**.

## 4. Fișierele din `data/`

The only thing explicit in `app.py` is:

- `os.makedirs("data", exist_ok=True)`

This means the application expects a local `data/` directory.

However, **the actual filenames inside `data/` are not shown in the provided code**, so for each file below the exact path is **nu reiese din cod** unless named through imported constants or function names.

### What can be inferred

The code strongly suggests persistent caches for:

- config
- portfolio snapshot
- portfolio history
- dividends status/cache
- ratings status/cache
- quality cache
- market context cache

### Writers and readers

#### Config file
- Writer: `save_config()`
- Reader: `load_config()`
- Exposed in UI via `CONFIG_FILE`

#### Portfolio snapshot cache
- Writer: `fetch_and_cache_core()`
- Reader: `load_cached_snapshot()`

#### Portfolio history
- Writer: `record_portfolio_point()`
- Reader: `load_portfolio_history()`

#### Dividend cache / status
- Writer: `start_dividends_fetch_background()`
- Reader: `load_cached_dividends()`, `load_dividends_status()`

#### Ratings cache / status
- Writer: `start_ratings_fetch_background()`
- Reader: `load_cached_ratings()`, `load_ratings_status()`

#### Quality cache
- Writer: `start_quality_fetch_background()`
- Reader: `load_quality_cache()`

#### Market context cache
- Writer: **nu reiese din cod**
- Reader: `load_market_context_cache()`

#### Dismissed alerts / alert state
- Writer: `dismiss_alert()`
- Reader: `check_loss_to_profit_alerts()`

Because the storage filenames are not shown, the exact `data/` file list is **nu reiese din cod**.

## 5. Data flow from source to screen

## A. Main page

### 1) Loading and configuration
- The app loads config with `load_config()`.
- Sidebar fields are populated from that config:
  - API key ID
  - API secret
  - refresh interval
- Saving writes to disk via `save_config()`.

### 2) Background scheduler
- `start_background_scheduler()` is called immediately after startup.
- The implementation is not shown, but it is responsible for automatic background updates.

### 3) Cached snapshot
- The main view uses `load_cached_snapshot()`.
- If no snapshot exists, the app shows an info message and stops.

### 4) Alerts
- If snapshot positions exist, the code builds a ticker-to-name map from instruments.
- `check_loss_to_profit_alerts()` is called.
- Alerts not marked as dismissed are displayed.
- Clicking “Am văzut” calls `dismiss_alert()` and reruns the app.

### 5) Core refresh button
- “Actualizează acum” calls `fetch_and_cache_core(api_key_id, api_secret)`.
- Then the app reruns.

### 6) Data preparation
Once snapshot data exists, the app computes:

- invested capital
- profit/loss
- market value
- yield percentage
- per-position current value
- acquisition cost
- per-position return %
- FX-adjusted acquisition cost in account currency
- dividend totals
- dividend yield on invested capital
- total return %
- ratings labels
- quality score/rating
- S&P 500 return
- PEG ratio
- alpha versus S&P 500

### 7) Summary metrics and chart
The app shows:
- Total Invested
- Market Value
- Yield
- Total Dividends Received

Then it loads portfolio history with `load_portfolio_history()` and, if at least two points exist, renders a Plotly line chart.

### 8) Positions table
The table is built from `df_display` and includes:
- name
- currency
- quantity
- average price
- current price
- acquisition cost
- current value
- P/L in account currency
- return %
- dividends
- dividend yield %
- total return %
- S&P 500 %
- holding days
- PEG
- alpha vs S&P 500
- recommendation
- score
- rating

The “Nume” column becomes a link to the detail view through query params.

## B. Detail page

### Trigger
The detail page is shown when:

- `selected_ticker` and `selected_row` are present in `st.session_state`

Then:

- `render_detail_view(...)` is called from `detail_view`

### Entry mechanisms
The selected position can be set by:
- choosing a name in the selectbox and pressing “Deschide →”
- clicking the link in the positions table
- using `?detail=<ticker>` query parameter

### What is passed
The detail view receives:
- selected row as a dictionary
- total portfolio value
- API key ID
- API secret

The detail view implementation is not included here, so what it displays is **nu reiese din cod**.

## C. Background threads / jobs

## 1) Scheduler
- `start_background_scheduler()` starts automatic periodic work.
- Exact mechanics and frequency are **nu reiese din cod**.

## 2) Dividends background fetch
Triggered by button:
- `start_dividends_fetch_background(api_key_id, api_secret, tickers_now)`

Status and progress:
- `load_dividends_status()`
- The UI shows `done / total` while in progress.

Data exposed to the UI:
- `load_cached_dividends()`

## 3) Ratings background fetch
Triggered by button:
- `start_ratings_fetch_background(tickers_now)`

Status and progress:
- `load_ratings_status()`

Data exposed to the UI:
- `load_cached_ratings()`

## 4) Quality background fetch
Triggered by:
- `start_quality_fetch_background(tickers_now)`

Data exposed to the UI:
- `load_quality_cache()`

The app triggers quality and ratings fetch together when the “recomandări” button is used.

## 6. Generated results: indicators, scores, charts, formulas

## Portfolio-level indicators

### 1) Invested capital
- `invested = cash.get("invested", 0.0)`

### 2) Profit/loss
- `ppl = cash.get("ppl", 0.0)`

### 3) Market value
- `market_value = invested + ppl`

### 4) Yield
- `yield_pct = (ppl / invested * 100.0) if invested else 0.0`

### 5) Total dividends
- `total_dividende = df["dividende_incasate"].sum()`

## Per-position indicators

### 1) Current value
- `valoare_curenta = quantity * currentPrice`

### 2) Acquisition cost
- `cost_achizitie = quantity * averagePrice`

### 3) Return %
Formula:
- `((currentPrice / averagePrice - 1) * 100).round(2)`

The code explicitly states this is based only on instrument price, without currency conversion.

### 4) GBX normalization
If `currencyCode == "GBX"`:
- `averagePrice /= 100`
- `currentPrice /= 100`
- `currencyCode = "GBP"`

This converts penny sterling instruments to GBP before calculations.

### 5) FX-adjusted acquisition cost
- `cost_achizitie_cont = cost_achizitie * fx_rate`

where `fx_rate` comes from:
- `fetch_fx_rate(ccy, account_currency)`

### 6) Dividends received
- `dividende_incasate = dividends.get(ticker, {}).get("total", 0.0)`

### 7) Dividend yield on invested capital
- `div_pe_investit_% = dividende_incasate / cost_achizitie_cont * 100`

### 8) Total return %
- `randament_total_% = randament_% + div_pe_investit_%`

### 9) Holding days
- `zile_detinut = days_held_from_iso(initialFillDate)`

### 10) S&P 500 return and alpha
- `sp500_return_%` is read from market context cache
- `alpha_% = randament_total_% - sp500_return_%`

## Ratings / quality outputs

### Recommendation
- `recomandare = ratings.get(ticker, "none")`

Then displayed via:
- `RECOMMENDATION_LABELS.get(v, v)`

### Quality score
- `Scor = round(quality_data.get(ticker, {}).get("total"), 1)` if available

### Rating
- `Rating = quality_data.get(ticker, {}).get("rating")`

## Charts

### Portfolio history chart
If `load_portfolio_history()` returns at least two points, the app renders a Plotly chart with:

- area/line trace for `market_value`
- dotted line trace for `invested`

The chart title is:
- “Valoare de piață în timp”

## 7. Configuration and running

## Dockerfile

The application is containerized with a standard Streamlit setup:

- Python 3.10 slim image
- dependencies installed from `requirements.txt`
- source copied into `/app`
- Streamlit exposed on port 8501
- run command:
  - `streamlit run app.py --server.port=8501 --server.address=0.0.0.0 --server.runOnSave=true`

## `requirements.txt`
This file is referenced by the Dockerfile, but its contents are **nu reiese din cod** because it is not included in the chat.

## `docker-compose`
No `docker-compose` file is present in the provided code, so its configuration is **nu reiese din cod**.

## Sidebar settings
The sidebar exposes:

- API key ID
- API secret
- automatic refresh interval in minutes
- save-to-disk button

It also shows whether:
- the config file exists on disk
- automatic refresh is active based on whether keys are filled in

### Persisted configuration
Saved via:
- `save_config(api_key_id, api_secret, interval_minutes)`

Loaded via:
- `load_config()`

### Config file path
Shown through:
- `CONFIG_FILE`

## 8. Limitations and fragile points visible in the code

1. **Several imports appear unused in `app.py`**
   - `requests`, `numpy`, `base64`, `json`, `threading`, `tempfile`, `px`, `components`
   - Also `fetch_benchmark_return`, `fetch_yahoo_peg_ratio`, `resolve_yahoo_symbol` are imported but **nu reiese din cod** that they are used here.

2. **Duplicate import**
   - `record_portfolio_point` is imported twice from `core`.

3. **Many implementation details are hidden in other modules**
   - Exact Trading 212 calls
   - exact Yahoo Finance behavior
   - cache file names
   - background scheduler logic
   - detail view behavior
   - all of these are **nu reiese din cod** from the supplied file contents

4. **Potential division by zero is handled only for invested capital**
   - `yield_pct` protects against zero invested
   - but `div_pe_investit_%` does **not** explicitly protect against zero `cost_achizitie_cont`
   - if acquisition cost is zero, this could produce infinite/invalid values

5. **Error handling is partial**
   - If `cash` or `portfolio` errors exist in snapshot, the app stops early
   - Other issues are only surfaced as captions/warnings

6. **The app depends heavily on cached data**
   - If caches are stale or missing, the UI degrades quickly
   - Many values are read from cache rather than fetched directly in the UI layer

7. **Query param based navigation is somewhat fragile**
   - It relies on `?detail=<ticker>`
   - It clears query params and reruns
   - If session state is inconsistent, the detail routing may not behave as expected

8. **Sorting/filtering state is only partially managed**
   - `positions_sort_label` and `positions_sort_desc` are initialized in session state
   - but they are not visibly used later in this file, so their purpose is **nu reiese din cod**

9. **Background update loop can rerun the app**
   - At the bottom, if dividends or ratings are in progress, the app sleeps 2 seconds and reruns
   - this can make the UI refresh loop feel aggressive

10. **Localization is mixed**
   - UI text is largely in Romanian
   - variable names and internal labels are mixed Romanian/English
   - this is not an error, but it makes maintenance less uniform

If you want, I can also turn this into a more formal document structure, for example:
- `README.md`
- `docs/architecture.md`
- `docs/data-flow.md`
