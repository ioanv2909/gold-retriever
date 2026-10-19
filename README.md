# GoldRetriever

Self-hosted portfolio analyzer for **Trading 212** and **XTB**, built with Streamlit.
It fetches your positions, prices and dividends, scores your holdings and shows returns across accounts
and currencies. Everything runs on your own server and your data stays on your disk.

> Not related to any cryptocurrency.

> **Disclaimer:** this software is provided for information only and is **not financial advice**.
> Market data comes from third parties (Yahoo Finance, justETF) and may be delayed or inaccurate.
> The project is not affiliated with Trading 212, XTB, Yahoo or justETF. Use at your own risk.

## Features

- **Trading 212** through the official API (positions, cash, dividends, order history).
- **XTB** through statement import (.xlsx), several accounts supported (XTB has no public API).
- Market data from Yahoo Finance and justETF.
- Quality score, risk score and ETF score, plus a "before buying" checklist and signals.
- Multi-account, multi-currency totals and history; the display currency is chosen from a dropdown.
- Returns over a period, including XIRR computed from deposits.
- Watchlist, alerts and per-position notes.
- Multiple users with separate data and an admin page.
- Interface in English and Romanian.

## Quick start (Docker)

```
git clone https://github.com/ioanv2909/gold-retriever.git
cd gold-retriever
docker compose up -d --build
```

Open http://localhost:8501. On first start you will be asked to create the **administrator account**.
Then add your Trading 212 API key from the sidebar and/or import XTB statements.
To use another port: `PORT=8502 docker compose up -d --build`.

Update with `git pull && docker compose up -d --build`.

## Data and privacy

- All data lives in `./data` (one folder per user under `data/users/`). Back it up.
- API keys are stored **in plain text** in that folder. Create a **read-only** Trading 212 API key and keep `./data` private.
- The app sends no telemetry. It contacts Trading 212, Yahoo Finance and justETF to fetch data.

## Security notes

- Do not expose the app directly to the internet. Put it behind a reverse proxy with HTTPS.
- The first account created becomes the administrator, so create it before exposing the app to a network.

## Roadmap

- Demo mode with sample data.
- Automated tests and pinned dependency versions.

## Documentation

Technical notes (in Romanian) are in [`DOCS.md`](DOCS.md) and [`docs/`](docs/).
Translation helpers are in [`tools/`](tools/).

## Descriere in romana

GoldRetriever este un analizor de portofoliu self-hosted pentru Trading 212 si XTB. Datele raman pe serverul tau.
Porneste cu `docker compose up -d --build`, deschide http://localhost:8501 si creeaza contul de administrator.
Nu este sfat financiar.

## License

MIT, see [LICENSE](LICENSE).
