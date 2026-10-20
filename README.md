# GoldRetriever

<p align="center"><img src="assets/icon-192.png" width="96" alt="GoldRetriever logo"></p>

A self-hosted portfolio analyzer for **Trading 212** and **XTB**, built with Streamlit. Your data stays on your own machine.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/screenshots/main-dark.png">
  <img src="docs/screenshots/main-light.png" alt="GoldRetriever portfolio summary">
</picture>

## Screenshots

| Dark | Light |
| --- | --- |
| <img src="docs/screenshots/main-dark.png" alt="Portfolio summary, dark theme"> | <img src="docs/screenshots/main-light.png" alt="Portfolio summary, light theme"> |
| <img src="docs/screenshots/login-dark.png" alt="Sign in, dark theme"> | <img src="docs/screenshots/login-light.png" alt="Sign in, light theme"> |

## Features

- Trading 212 (API) and XTB (xlsx report import) in one view, with any number of accounts
- Display in any currency, chosen per user; exchange rates from Yahoo Finance
- Market value over time (value vs. invested), return summary and XIRR
- Per-position profit/loss, dividends, and comparison with the S&P 500 over the same holding period
- Quality and risk scores, analyst ratings, ETF data from justETF
- Watchlist and loss-to-profit alerts
- Detail page for every instrument
- Multi-user: separate data per user, admin page for accounts, signed login cookie
- Romanian and English interface

## Quick start

```bash
git clone https://github.com/ioanv2909/gold-retriever.git
cd gold-retriever
docker compose up -d --build
```

Open http://localhost:8501. On the first visit you create the admin account. To use another port: `PORT=8080 docker compose up -d`. Everything you add is stored in `./data`.

## Connect your accounts

- **Trading 212:** sidebar, *Trading 212 authentication*. Enter an API key ID and secret (create the key with read-only permissions).
- **XTB:** sidebar, *XTB — import*. Upload the xlsx account report (sheets *Open Positions*, *Cash Operations*, *Closed Positions*). You can import several accounts (EUR, USD, RON, ...).

## Try the demo

Creates a `demo` user with a fictional portfolio: real tickers and real prices, invented purchases. It needs internet access for the prices.

```bash
docker compose exec gold-retriever python tools/make_demo.py
docker compose exec gold-retriever python tools/make_demo_t212.py
docker compose exec gold-retriever python tools/make_demo_history.py
```

Log in as `demo` / `demo`.

## Security notes

- API keys are stored in plain text in `data/users/<name>/config.json`. Protect the `data` folder.
- There is no built-in HTTPS. Put the app behind a reverse proxy or a VPN before exposing it to the internet.
- The first visitor creates the admin account, so do it right after starting the app.
- The container runs as root, so files in `data/` are owned by root.

## Development

Python 3.10, dependencies in `requirements.txt`. CI compiles the code and checks that every import resolves. To regenerate the screenshots of the demo account:

```bash
docker run --rm --network host -v "$PWD":/w mcr.microsoft.com/playwright/python:v1.49.0-noble \
  sh -c "pip install -q --break-system-packages playwright==1.49.0 && python /w/tools/screenshots.py"
```

## License and credits

MIT, see `LICENSE`. The dog in the logo is derived from Noto Emoji (Google, Apache License 2.0), see `assets/NOTICE-artwork.txt`.

This is not financial advice. The project is not affiliated with Trading 212, XTB, Yahoo or justETF; check their terms before using their data.

## Support

GoldRetriever is free and open source. If it is useful to you, you can support its development:

[![Ko-fi](https://img.shields.io/badge/Ko--fi-Support%20the%20project-FF5E5B?logo=ko-fi&logoColor=white)](https://ko-fi.com/goldretriever)
