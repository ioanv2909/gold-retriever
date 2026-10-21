# Data flow

## Sources -> caches -> screen

Every external call writes into a JSON cache; the UI only reads caches. A
refresh therefore never makes a page load slow or fail.

    Trading 212 API --> portfolio_cache.json, account_info_cache.json,
                        dividends_cache.json, t212_fills.json, t212_flows.json
    XTB xlsx upload --> xtb.json (+ xtb_prices.json from Yahoo)
    Yahoo / justETF --> quality_cache.json, market_context_cache.json,
                        justetf_cache.json, ratings_cache.json, events_cache.json,
                        exposure_cache.json, strategy_cache.json
    caches ------------> app.py computes rows and totals --> screen

## Trading 212

1. Keys are saved per user in `config.json` (Settings -> Trading 212).
2. A refresh calls the API and stores the snapshot: cash, positions,
   instruments and any errors.
3. Dividends and deposits/withdrawals come from the account history.
4. Executed orders (`t212_fills.json`) plus Yahoo daily closes are used to
   rebuild a daily value history (`t212_history_reconstructed.json`).

## XTB

1. The user uploads an XTB xlsx report (Settings -> XTB import).
2. `parse_xtb_file` reads Open Positions, Cash Operations and Closed
   Positions and runs consistency checks (cash sum, total row, positions value).
3. `import_xtb` merges it into `xtb.json`, keyed by account (currency plus a
   short hash of the account number).
4. Prices come from Yahoo (`xtb_prices.json`); quantity and cost come from
   the report. History is rebuilt from purchases (`xtb_history_reconstructed.json`).

## Currency

Each position keeps its own currency. Cost, value, P/L and dividends are
converted at the current rate to the chosen display currency via
`portfolio_model.fx`: direct rate first, otherwise through USD; results are
cached for 10 minutes. Penny currencies (GBX) are normalised to GBP.

## Returns

- Simple return: current price against average price.
- Total return: simple return plus dividends over cost.
- Period return: XIRR from deposits and withdrawals (`returns_summary.py`);
  estimates for XTB and for the total.
- Comparison with the S&P 500 over the same holding period, with an
  annualised version.

## History chart

`portfolio_history.json` and `portfolio_history_multi.json` hold value and
cost points over time. The reconstructed files fill the past; new points are
recorded on refresh. The chart can start at an amount threshold and be
filtered by period (3H, 1D, 1W, 1M, 1Y, YTD, Max). YTD is the default, and the
period chosen here is carried over to the position charts.

## Refresh

- Manual: Settings -> Updates.
- Automatic: a background scheduler at the interval saved in the config.
- Dividends, ratings, quality and prices run in separate threads with status
  files, so progress can be shown and a failure in one does not block the rest.
- Events calendar: once an hour the scheduler fetches earnings and dividend
  dates (Yahoo Finance) for tickers older than 12 hours into `events_cache.json`,
  then sends the user a digest of new events if they opted in (Settings ->
  Calendar). Already sent events are kept in `events_notified.json`.
