# Architecture

## Overview

This application is a Streamlit-based local portfolio analyzer for Trading212. It is organized around a main UI entry point and a small set of helper modules responsible for data fetching, caching, background refreshes, and detailed position rendering.

## Components

### `app.py`
Main Streamlit application. Responsibilities:

- render the sidebar configuration UI
- load cached configuration and data
- trigger manual and background refreshes
- compute and display portfolio metrics
- build the positions table
- route to the detailed view when a position is selected

### `core.py`
Core persistence and business logic helpers. Responsibilities include:

- loading and saving config
- tracking alerts
- recording portfolio history
- dismissing notifications

### `t212_api.py`
Trading212 API integration and cache access. Responsibilities include:

- fetching account data
- fetching and caching portfolio snapshots
- fetching account currency
- fetching FX rates
- loading cached dividend/rating/snapshot data

### `yahoo.py`
Yahoo Finance data access. Responsibilities include:

- resolving symbols
- fetching PEG ratios
- fetching benchmark returns such as S&P 500 comparison

### `background.py`
Background orchestration. Responsibilities include:

- scheduling periodic refreshes
- tracking status for background jobs
- starting dividend, ratings, and quality refresh tasks
- storing market context cache

### `detail_view.py`
Detailed instrument analysis UI. Responsibilities include:

- rendering per-position detail pages
- supporting navigation back to the main table
- keeping the detail view scroll position usable

## Runtime flow

1. The app starts and loads configuration.
2. Background scheduling is initialized.
3. The UI renders the main view.
4. Cached portfolio data is loaded.
5. Optional updates may be triggered manually or in the background.
6. The table and summary metrics are computed from the latest cached snapshot.
7. If a position is selected, the detail view is rendered.

## Data dependencies

The UI depends on multiple data sources:

- Trading212 account and portfolio data
- FX rates
- dividend history
- ratings and quality data
- Yahoo Finance benchmark data
- local caches and persisted config

## UI structure

The application has two main modes:

- **Main portfolio view**
  - summary metrics
  - alerts
  - refresh buttons
  - open positions table
  - history chart

- **Detail view**
  - instrument-specific performance analysis
  - selected row data
  - per-position insights

## Background tasks

Background jobs are used to avoid blocking the UI for slower refresh operations. These tasks update cached data and expose progress through status helpers.

## Design goals

- keep the UI responsive
- prefer cached data for fast startup
- isolate external API calls in helper modules
- make portfolio analysis reproducible and local-first
