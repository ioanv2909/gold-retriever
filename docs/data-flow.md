# Data Flow

## Overview

This document describes how data moves through the application.

## Input sources

### User-provided credentials
Entered in the Streamlit sidebar:

- API key ID
- API secret
- refresh interval

### Trading212 data
Used for:

- account cash
- portfolio positions
- instrument metadata
- dividends

### External market data
Used for:

- benchmark comparison
- PEG ratio
- symbol resolution
- FX conversion

### Local caches and config
Stored on disk for:

- persistent config
- cached snapshot data
- cached dividends
- cached ratings
- cached quality data
- portfolio history
- alert dismissal state

## Main flow

### 1. App startup
- `app.py` loads config.
- Sidebar inputs are populated from disk.
- Background scheduler is started.

### 2. Snapshot loading
- Cached portfolio snapshot is loaded.
- If available, positions and cash are extracted.
- Errors are checked before rendering.

### 3. Position enrichment
The app converts raw positions into a dataframe and enriches them with:

- instrument name
- currency code
- current price and cost basis normalization
- FX conversion to account currency
- dividend totals
- recommendation labels
- quality score and rating
- market comparison values

### 4. Metric computation
The app computes:

- invested capital
- market value
- unrealized P/L
- total yield
- total dividends
- per-position return
- dividend yield relative to invested capital
- total return
- alpha versus S&P 500

### 5. Rendering
The main view shows:

- warnings and alerts
- summary metrics
- history chart
- status messages
- open positions table

### 6. Detail routing
If a position is selected:

- the selected ticker and row are stored in session state
- the detail view is rendered
- the app switches from table view to detailed analysis

## Background refresh flow

Background tasks can refresh:

- portfolio snapshot
- dividends
- ratings
- quality data
- market context

These tasks update caches and provide status such as in-progress, done, and total.

## Cache usage

The app is designed to prefer cached data when possible:

- faster startup
- reduced API calls
- smoother UI
- background refresh without blocking

## Important transformations

### GBX normalization
GBX values are converted to GBP before display and analysis so that pricing remains in a real currency unit.

### FX conversion
Instrument-currency cost basis is converted to account currency for dividend and invested-capital comparisons.

### Benchmark comparison
The app compares total position return with S&P 500 performance over the same holding period.

## Output

The final outputs shown to the user are:

- portfolio summary cards
- alert banners
- status captions
- positions table
- optional detailed analysis view
- portfolio history chart
