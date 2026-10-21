"""Texte RO/EN. Folosire: from i18n import t ; t("cheie") sau t("cheie", n=3) pentru {n} in text."""
import json
import os
import re

import streamlit as st

LANGS = ["RO", "EN"]

_T = {
    "app.title": {"RO": "GoldRetriever — Portfolio Analyzer", "EN": "GoldRetriever — Portfolio Analyzer"},
    "app.summary": {"RO": "📈 Sumar Portofoliu", "EN": "📈 Portfolio Summary"},
    "side.updates": {"RO": "🔄 Actualizări", "EN": "🔄 Updates"},
    "side.filters": {"RO": "🔎 Filtre", "EN": "🔎 Filters"},
    "side.xtb_import": {"RO": "📥 XTB — import", "EN": "📥 XTB — import"},
    "side.auth": {"RO": "🔑 Autentificare Trading 212", "EN": "🔑 Trading 212 authentication"},
    "btn.refresh_now": {"RO": "🔄 Actualizează acum", "EN": "🔄 Refresh now"},
    "btn.refresh_div": {"RO": "💵 Actualizează dividende (fundal)", "EN": "💵 Refresh dividends (background)"},
    "btn.refresh_div_busy": {"RO": "💵 Actualizare dividende...", "EN": "💵 Updating dividends..."},
    "btn.refresh_rat": {"RO": "🎯 Actualizează recomandări (fundal)", "EN": "🎯 Refresh ratings (background)"},
    "btn.refresh_rat_busy": {"RO": "🎯 Actualizare recomandări...", "EN": "🎯 Updating ratings..."},
    "filter.rating": {"RO": "Filtrează după recomandare", "EN": "Filter by rating"},
    "hist.variation": {"RO": "Variație profit în perioadă ({rng})", "EN": "Profit change over period ({rng})"},
    "hist.variation_help": {
        "RO": "Câștig/pierdere de piață, fără depuneri. % = față de media sumei investite pe perioadă.",
        "EN": "Market gain/loss, excluding deposits. % = relative to the average amount invested over the period.",
    },
    "ret.title": {"RO": "📈 Randament pe perioadă", "EN": "📈 Return over period"},
    "ret.err": {"RO": "Nu am putut calcula randamentul: {e}", "EN": "Could not compute the return: {e}"},
    "ret.est": {
        "RO": "{name}: cost {cost} {ccy} | P/L {pl} | randament {r}% | vârsta medie a banilor ≈ {wage} ani",
        "EN": "{name}: cost {cost} {ccy} | P/L {pl} | return {r}% | average age of money ≈ {wage} yrs",
    },
    "ret.annual_est": {"RO": " | ≈ {a}%/an (estimare)", "EN": " | ≈ {a}%/yr (estimate)"},
    "ret.under_year": {"RO": " | sub un an, neanualizat", "EN": " | under a year, not annualized"},
    "ret.xirr_line": {
        "RO": "{name}: depus {inv} {ccy} | valoare {val} | câștig net {net} ({pct}%)",
        "EN": "{name}: deposited {inv} {ccy} | value {val} | net gain {net} ({pct}%)",
    },
    "ret.xirr_tail": {"RO": " | XIRR {x}%/an{extra}", "EN": " | XIRR {x}%/yr{extra}"},
    "ret.exact": {"RO": " (exact)", "EN": " (exact)"},
    "ret.estimate_tag": {"RO": " (estimare)", "EN": " (estimate)"},
    "ret.loading": {
        "RO": "Se descarcă istoricul depunerilor T212 (~1 minut); reîncarcă pagina. Până atunci: estimare.",
        "EN": "Downloading the T212 deposit history (~1 minute); reload the page. Until then: estimate.",
    },
    "ret.ref": {
        "RO": "Perioada de referință: de la {d} (prima depunere reală), {y} ani.",
        "EN": "Reference period: since {d} (first real deposit), {y} years.",
    },
    "ret.xirr_q": {"RO": "ℹ️ Ce este XIRR? (trece cu mouse-ul)", "EN": "ℹ️ What is XIRR? (hover)"},
    "ret.xirr_help": {
        "RO": "XIRR este randamentul anualizat care ține cont de data fiecărei depuneri. Răspunde la: cu ce dobândă anuală compusă ar fi crescut banii depuși, la datele reale, ca să ajungă la valoarea de azi. Spre deosebire de împărțirea simplă a câștigului la ani, nu tratează banii noi la fel ca cei vechi. Se poate compara direct cu un indice sau cu un depozit; sub un an nu îl afișez, fiindcă ar înșela.",
        "EN": "XIRR is the annualized return that accounts for the date of each deposit. It answers: at what compound annual rate would the money you deposited have had to grow, on the actual dates, to reach today's value. Unlike simply dividing the gain by the years, it does not treat new money like old money. It can be compared directly with an index or a deposit rate; under one year it is not shown, because it would mislead.",
    },
    "ret.foot": {
        "RO": "T212: XIRR exact din depuneri/retrageri. XTB și Total: estimare (XTB, fără istoric de depuneri; Total folosește costul pozițiilor XTB la data primei cumpărări și cursul de azi). Pozițiile vândute nu intră în estimări.",
        "EN": "T212: exact XIRR from deposits/withdrawals. XTB and Total: estimates (XTB has no deposit history; Total uses the cost of XTB positions at the first purchase date and today's FX rate). Sold positions are not included in estimates.",
    },
    "alert.seen": {"RO": "Am văzut", "EN": "Seen"},
    "side.auto_on": {"RO": "🔄 Actualizare automată activă, la fiecare {n} min.", "EN": "🔄 Auto-refresh on, every {n} min."},
    "side.auto_off": {"RO": "🔄 Actualizare automată inactivă — completează și salvează cheile API.", "EN": "🔄 Auto-refresh off — enter and save the API keys."},
    "main.updated_at": {"RO": "🕒 Poziții/cash actualizate: {ts}", "EN": "🕒 Positions/cash updated: {ts}"},
    "main.no_cache": {
        "RO": "Nu există încă date în cache. Apasă „Actualizează acum” sau așteaptă primul ciclu automat.",
        "EN": "No cached data yet. Press “Refresh now” or wait for the first automatic cycle.",
    },
    "main.no_positions": {"RO": "Nu există poziții deschise.", "EN": "No open positions."},
    "main.portfolios": {"RO": "Portofolii", "EN": "Portfolios"},
    "main.display_ccy": {"RO": "Monedă", "EN": "Currency"},
    "hist.accumulating": {
        "RO": "Istoricul se acumulează la fiecare 15 minute; graficul apare după al doilea punct.",
        "EN": "History accumulates every 15 minutes; the chart appears after the second point.",
    },
    "hist.points": {"RO": "{n} puncte · {a} → {b}", "EN": "{n} points · {a} → {b}"},
    "hist.incomplete": {
        "RO": "Istoricul disponibil începe la {d}; perioada aleasă începe mai devreme, deci graficul e incomplet.",
        "EN": "Available history starts at {d}; the chosen period starts earlier, so the chart is incomplete.",
    },
    "hist.enlarge": {"RO": "⤢ Mărește graficul", "EN": "⤢ Enlarge chart"},
    "main.cash_xtb": {"RO": "Cash XTB: {items} · total {total} {ccy}", "EN": "XTB cash: {items} · total {total} {ccy}"},
    "main.cash_t212": {"RO": "Cash T212", "EN": "T212 cash"},
    "main.cash_acct": {"RO": "Cash {label}", "EN": "{label} cash"},
    "main.cash_total": {"RO": "Total cash", "EN": "Total cash"},
    "main.cash_sub": {"RO": "Rezervat pt. ordine: {blocked} · Rezultat realizat (all-time): {result}", "EN": "Reserved for orders: {blocked} · Realized result (all-time): {result}"},
    "ret.unavailable": {"RO": "Randament indisponibil: {e}", "EN": "Return unavailable: {e}"},
    "div.running": {"RO": "🔄 Actualizare dividende în fundal: {done}/{tot} poziții verificate.", "EN": "🔄 Updating dividends in the background: {done}/{tot} positions checked."},
    "div.updated": {"RO": "🕒 Dividende actualizate: {ts}", "EN": "🕒 Dividends updated: {ts}"},
    "div.none": {"RO": "🕒 Dividende: neactualizate încă.", "EN": "🕒 Dividends: not updated yet."},
    "div.partial_err": {"RO": "⚠️ Dividendele nu s-au putut actualiza complet: {e}", "EN": "⚠️ Dividends could not be fully updated: {e}"},
    "rat.running": {"RO": "🔄 Actualizare recomandări în fundal: {done}/{tot} poziții verificate.", "EN": "🔄 Updating ratings in the background: {done}/{tot} positions checked."},
    "rat.updated": {"RO": "🕒 Recomandări actualizate: {ts}", "EN": "🕒 Ratings updated: {ts}"},
    "rat.none": {"RO": "🕒 Recomandări: neactualizate încă.", "EN": "🕒 Ratings: not updated yet."},
    "main.open_positions": {"RO": "📋 Poziții deschise", "EN": "📋 Open positions"},
    "filter.active": {"RO": "🔎 Filtru activ: {f} (se schimbă din meniul lateral)", "EN": "🔎 Active filter: {f} (change it from the side menu)"},
    "filter.none": {"RO": "Nicio poziție nu se potrivește cu filtrul ales.", "EN": "No position matches the chosen filter."},
    "table.sort_hint": {"RO": "Sortează direct din antetul tabelului.", "EN": "Sort directly from the table header."},
    "table.click_hint": {"RO": "Click pe un rând din tabel pentru analiza detaliată.", "EN": "Click a table row for the detailed analysis."},
    "tab.positions": {"RO": "Poziții", "EN": "Positions"},
    "tab.watchlist": {"RO": "👁️ Watchlist", "EN": "👁️ Watchlist"},
    "wl.symbol": {"RO": "Simbol Yahoo Finance (ex. NVDA, SAP.DE, VUSA.L)", "EN": "Yahoo Finance symbol (e.g. NVDA, SAP.DE, VUSA.L)"},
    "wl.isin": {"RO": "ISIN (opțional, doar ETF)", "EN": "ISIN (optional, ETFs only)"},
    "wl.add": {"RO": "Adaugă", "EN": "Add"},
    "wl.remove_label": {"RO": "Șterge din watchlist", "EN": "Remove from watchlist"},
    "wl.remove": {"RO": "Șterge", "EN": "Delete"},
    "wl.refresh": {"RO": "Actualizează acum", "EN": "Refresh now"},
    "wl.started": {"RO": "Actualizare pornită în fundal; reîncarcă pagina peste un minut.", "EN": "Update started in the background; reload the page in a minute."},
    "wl.empty": {"RO": "Watchlist-ul e gol. Adaugă un simbol de pe Yahoo Finance.", "EN": "The watchlist is empty. Add a symbol from Yahoo Finance."},
    "xtb.import": {"RO": "Importă", "EN": "Import"},
    "xtb.hide_report": {"RO": "Ascunde raportul", "EN": "Hide report"},
    "xtb.no_data": {"RO": "Nu există încă date XTB.", "EN": "No XTB data yet."},
    "xtb.symbols_title": {"RO": "**Simboluri și prețuri**", "EN": "**Symbols and prices**"},
    "xtb.save_symbols": {"RO": "Salvează simbolurile", "EN": "Save symbols"},
    "xtb.refresh_prices": {"RO": "Actualizează prețurile acum", "EN": "Refresh prices now"},
    "xtb.prices_started": {"RO": "Actualizare pornită; reîncarcă pagina peste un minut.", "EN": "Update started; reload the page in a minute."},
    "xtb.prices_busy": {"RO": "O actualizare e deja în curs sau nu există conturi XTB.", "EN": "An update is already running or there are no XTB accounts."},
    "xtb.save_isin": {"RO": "Salvează ISIN", "EN": "Save ISIN"},
    "xtb.no_isin_changes": {"RO": "Nu există modificări ISIN de salvat.", "EN": "No ISIN changes to save."},
    "xtb.isin_saved": {"RO": "{n} ISIN-uri salvate.", "EN": "{n} ISINs saved."},
    "xtb.check_isin": {"RO": "Verifică toate ISIN-urile", "EN": "Check all ISINs"},
    "xtb.no_issues": {"RO": "Nicio problemă găsită.", "EN": "No issues found."},
    "xtb.allow_delete": {"RO": "Permite ștergerea unui cont XTB", "EN": "Allow deleting an XTB account"},
    "xtb.delete_account": {"RO": "Șterge contul", "EN": "Delete account"},
    "alert.loss_to_profit": {
        "RO": "⚠️ **{name} ({ticker})** — ținută de {days} zile, tocmai a trecut de pe pierdere pe profit (+{pct}%). Merită să decizi acum dacă o mai ții sau o vinzi.",
        "EN": "⚠️ **{name} ({ticker})** — held for {days} days, has just moved from a loss to a profit (+{pct}%). Worth deciding now whether to keep or sell it.",
    },
    "main.table_note": {
        "RO": "Costul, valoarea, P/L și dividendele sunt în {ccy} (conversie la cursul curent); prețurile și cantitățile sunt în moneda instrumentului. Pozițiile XTB au prețuri de la Yahoo Finance, iar cantitatea și costul vin din ultimul export XTB.",
        "EN": "Cost, value, P/L and dividends are in {ccy} (converted at the current rate); prices and quantities are in the instrument's currency. XTB positions use Yahoo Finance prices, while quantity and cost come from the latest XTB export.",
    },
    "main.fx_error": {"RO": " · ⚠️ curs valutar: {e}", "EN": " · ⚠️ FX rate: {e}"},
    "main.alpha_note": {
        "RO": "Coloana `vs S&P500 pp` este afișată automat și compară randamentul total al poziției cu randamentul total al S&P 500 pe exact aceeași perioadă de deținere; valorile sunt `n/a` când lipsesc datele necesare sau Yahoo Finance nu poate răspunde.",
        "EN": "The `vs S&P500 pp` column is shown automatically and compares the position's total return with the S&P 500's total return over exactly the same holding period; values are `n/a` when the required data is missing or Yahoo Finance cannot respond.",
    },
    "hold.title": {"RO": "📌 Pozițiile tale", "EN": "📌 Your positions"},
    "hold.qty": {"RO": "Cantitate", "EN": "Quantity"},
    "hold.avg": {"RO": "Preț mediu", "EN": "Avg price"},
    "hold.px": {"RO": "Preț curent", "EN": "Current price"},
    "hold.cost": {"RO": "Cost", "EN": "Cost"},
    "hold.value": {"RO": "Valoare", "EN": "Value"},
    "hold.price_ret": {"RO": "Randament din preț", "EN": "Price return"},
    "hold.div": {"RO": "Dividende încasate", "EN": "Dividends received"},
    "hold.of_cost": {"RO": "{p}% din cost", "EN": "{p}% of cost"},
    "hold.total_ret": {"RO": "Randament total", "EN": "Total return"},
    "hold.weight": {"RO": "Pondere în portofoliu", "EN": "Portfolio weight"},
    "hold.days": {"RO": "Zile deținut: {n}", "EN": "Days held: {n}"},
    "hold.total_title": {"RO": "**Total** ({ccy}, conversie la cursul curent)", "EN": "**Total** ({ccy}, converted at the current rate)"},
    "hold.total_qty": {"RO": "Cantitate totală", "EN": "Total quantity"},
    "hold.note_t212": {"RO": "date de la Trading 212", "EN": "data from Trading 212"},
    "hold.note_xtb": {"RO": "cantitatea și costul vin din exportul XTB de la {report}", "EN": "quantity and cost come from the XTB export of {report}"},
    "hold.note_price": {"RO": "preț din export, nu de la Yahoo", "EN": "price from the export, not from Yahoo"},
    "hold.expander": {"RO": "Cumpărări și dividende — {title}", "EN": "Purchases and dividends — {title}"},
    "hold.col.date": {"RO": "Data", "EN": "Date"},
    "hold.col.qty": {"RO": "Cantitate", "EN": "Quantity"},
    "hold.col.price": {"RO": "Preț (moneda instrumentului)", "EN": "Price (instrument currency)"},
    "hold.col.amount": {"RO": "Sumă (moneda contului)", "EN": "Amount (account currency)"},
    "hold.col.type": {"RO": "Tip", "EN": "Type"},
    "hold.help.qty": {"RO": "Numărul de acțiuni/unități deținute în acest portofoliu.", "EN": "Number of shares/units held in this portfolio."},
    "hold.help.avg": {"RO": "Prețul mediu de achiziție, în moneda instrumentului.", "EN": "Average purchase price, in the instrument's currency."},
    "hold.help.px": {
        "RO": "Prețul curent, în moneda instrumentului (de la Trading 212 pentru pozițiile de acolo, de la Yahoo Finance pentru XTB).",
        "EN": "Current price, in the instrument's currency (from Trading 212 for positions held there, from Yahoo Finance for XTB).",
    },
    "hold.help.cost": {
        "RO": "Cât ai plătit în total pentru poziție, în moneda contului: valoarea curentă minus profitul (P/L) raportat. Include efectul cursului valutar de la momentul achiziției, deci poate diferi de cantitate × preț mediu × cursul de azi.",
        "EN": "Total amount paid for the position, in the account currency: current value minus the reported profit (P/L). It includes the FX effect at the time of purchase, so it may differ from quantity × average price × today's rate.",
    },
    "hold.help.value": {
        "RO": "Cantitatea × prețul curent, în moneda contului: cât valorează poziția dacă ai vinde-o la prețul afișat.",
        "EN": "Quantity × current price, in the account currency: what the position is worth if sold at the displayed price.",
    },
    "hold.help.pl": {
        "RO": "Profit sau pierdere nerealizată, în moneda contului. La Trading 212 e cifra raportată de platformă (include efectul cursului de la achiziție); la XTB, valoarea curentă minus costul din export.",
        "EN": "Unrealized profit or loss, in the account currency. For Trading 212 it is the figure reported by the platform (it includes the FX effect from the time of purchase); for XTB, current value minus the cost from the export.",
    },
    "hold.help.ret": {
        "RO": "(Preț curent / Preț mediu − 1) × 100. Randament pur din mișcarea prețului, în moneda instrumentului.",
        "EN": "(Current price / Average price − 1) × 100. Pure price return, in the instrument's currency.",
    },
    "hold.help.div": {
        "RO": "Dividendele încasate, în moneda contului (la XTB, nete de impozitul reținut). Sub valoare: dividendele raportate la costul de achiziție (yield on cost).",
        "EN": "Dividends received, in the account currency (for XTB, net of withholding tax). Below the value: dividends relative to the purchase cost (yield on cost).",
    },
    "hold.help.tot": {
        "RO": "Randament din preț plus dividendele raportate la cost: o aproximare simplă a randamentului total.",
        "EN": "Price return plus dividends relative to cost: a simple approximation of the total return.",
    },
    "hold.help.weight": {
        "RO": "Cât din valoarea pozițiilor din acest portofoliu reprezintă poziția asta. Reper: sub 5-10% per poziție e considerat rezonabil diversificat; peste 20% înseamnă că performanța ei îți afectează puternic tot portofoliul.",
        "EN": "How much of this portfolio's positions value this position represents. Rule of thumb: under 5–10% per position is considered reasonably diversified; above 20% means its performance strongly affects your whole portfolio.",
    },
    "dv.chart_title": {"RO": "📈 Grafic preț", "EN": "📈 Price chart"},
    "dv.period": {"RO": "Perioadă", "EN": "Period"},
    "dv.per.1Z": {"RO": "1Z", "EN": "1D"},
    "dv.per.1S": {"RO": "1S", "EN": "1W"},
    "dv.per.1L": {"RO": "1L", "EN": "1M"},
    "dv.per.3L": {"RO": "3L", "EN": "3M"},
    "dv.per.YTD": {"RO": "YTD", "EN": "YTD"},
    "dv.per.1A": {"RO": "1A", "EN": "1Y"},
    "dv.per.5A": {"RO": "5A", "EN": "5Y"},
    "dv.per.Max": {"RO": "Max", "EN": "Max"},
    "dv.bought": {"RO": "Cumpărat", "EN": "Bought"},
    "dv.bought_here": {"RO": "Cumpărat aici", "EN": "Bought here"},
    "dv.buy_marker_note": {
        "RO": "Marcajul „Cumpărat aici” folosește prețul de închidere Yahoo cel mai apropiat de data primei tranzacții raportate de broker (Trading 212 sau XTB) — poate diferi puțin de prețul mediu real din platformă (clasă de acțiuni, monedă, tranzacții multiple).",
        "EN": "The “Bought here” marker uses the Yahoo closing price nearest to the date of the first transaction reported by the broker (Trading 212 or XTB) — it may differ slightly from the real average price on the platform (share class, currency, multiple transactions).",
    },
    "dv.back": {"RO": "← Înapoi la portofoliu", "EN": "← Back to portfolio"},
    "dv.map_label": {"RO": "Simbol Yahoo Finance (corectează dacă maparea automată e greșită)", "EN": "Yahoo Finance symbol (correct it if the automatic mapping is wrong)"},
    "dv.save_map": {"RO": "💾 Salvează maparea", "EN": "💾 Save mapping"},
    "dv.saved": {"RO": "Salvat.", "EN": "Saved."},
    "dv.description": {"RO": "📄 Descriere companie / ETF", "EN": "📄 Company / ETF description"},
    "dv.etf_score_title": {"RO": "🏆 Scor ETF", "EN": "🏆 ETF score"},
    "dv.etf_no_isin": {"RO": "Nu s-a putut identifica ISIN-ul ETF-ului pentru calculul scorului.", "EN": "Could not identify the ETF's ISIN to compute the score."},
    "dv.etf_no_data": {"RO": "Nu s-au putut extrage date suficiente pentru calculul scorului ETF.", "EN": "Could not extract enough data to compute the ETF score."},
    "dv.etf_score": {"RO": "Scor ETF", "EN": "ETF score"},
    "dv.indicator_details": {"RO": "Detalii indicatori", "EN": "Indicator details"},
    "dv.etf_swap": {"RO": "ETF-ul folosește replicare swap.", "EN": "The ETF uses swap replication."},
    "dv.etf_domicile": {"RO": "Domiciliul ETF-ului este {d}, nu Ireland sau Luxembourg.", "EN": "The ETF is domiciled in {d}, not Ireland or Luxembourg."},
    "dv.etf_ter": {"RO": "TER ridicat: {v}% (> 0.60%).", "EN": "High TER: {v}% (> 0.60%)."},
    "dv.quality_title": {"RO": "🏆 Scor de calitate", "EN": "🏆 Quality score"},
    "dv.no_yf_quality": {"RO": "Pachetul `yfinance` nu este disponibil — scorul de calitate nu poate fi calculat.", "EN": "The `yfinance` package is not available — the quality score cannot be computed."},
    "dv.quality_no_data": {"RO": "Nu s-au putut extrage date suficiente pentru calculul scorului de calitate.", "EN": "Could not extract enough data to compute the quality score."},
    "dv.quality_score": {"RO": "Scor de calitate", "EN": "Quality score"},
    "dv.period_notes": {"RO": "Note perioadă: {n}", "EN": "Period notes: {n}"},
    "dv.risk_title": {"RO": "⚠️ Risc", "EN": "⚠️ Risk"},
    "dv.no_yf_risk": {"RO": "Pachetul `yfinance` nu este disponibil — scorul de risc nu poate fi calculat.", "EN": "The `yfinance` package is not available — the risk score cannot be computed."},
    "dv.risk_no_data": {"RO": "Nu s-au putut extrage date suficiente pentru calculul scorului de risc.", "EN": "Could not extract enough data to compute the risk score."},
    "dv.risk_score": {"RO": "Scor de risc", "EN": "Risk score"},
    "dv.risk_hint": {"RO": "Un scor mare înseamnă risc mai mic.", "EN": "A high score means lower risk."},
    "dv.orders_title": {"RO": "📜 Istoricul tranzacțiilor", "EN": "📜 Transaction history"},
    "dv.no_orders": {"RO": "Nicio tranzacție găsită pentru acest instrument.", "EN": "No transactions found for this instrument."},
    "dv.perf_title": {"RO": "📐 Performanța vs. piață", "EN": "📐 Performance vs. market"},
    "dv.needs_yf": {"RO": "Necesită `yfinance` — vezi avertismentul de mai jos.", "EN": "Requires `yfinance` — see the warning below."},
    "dv.no_fill_date": {"RO": "Nu pot calcula comparația — lipsește data de achiziție (`initialFillDate`) din datele T212.", "EN": "Cannot compute the comparison — the purchase date (`initialFillDate`) is missing from the T212 data."},
    "dv.bench_index": {"RO": "Index de comparație (Yahoo Finance)", "EN": "Comparison index (Yahoo Finance)"},
    "dv.your_return": {"RO": "Randamentul tău (total)", "EN": "Your return (total)"},
    "dv.bench_period": {"RO": "{sym} (aceeași perioadă)", "EN": "{sym} (same period)"},
    "dv.difference": {"RO": "Diferență", "EN": "Difference"},
    "dv.beat": {"RO": "Poziția a bătut {sym} cu {d} pp pe exact perioada de deținere.", "EN": "The position beat {sym} by {d} pp over exactly the holding period."},
    "dv.under": {"RO": "Poziția a fost sub {sym} cu {d} pp pe exact perioada de deținere.", "EN": "The position was below {sym} by {d} pp over exactly the holding period."},
    "dv.no_yf_installed": {"RO": "Pachetul `yfinance` nu e instalat — adaugă `yfinance` în requirements.txt și rebuild o dată.", "EN": "The `yfinance` package is not installed — add `yfinance` to requirements.txt and rebuild once."},
    "dv.fix_symbol": {"RO": "Corectează simbolul Yahoo Finance mai sus și salvează maparea, apoi reîncearcă.", "EN": "Correct the Yahoo Finance symbol above and save the mapping, then try again."},
    "dv.valuation_title": {"RO": "💵 Valuation fundamental", "EN": "💵 Fundamental valuation"},
    "dv.red_zone": {"RO": "{r} din {n} indicatori de valuare în zona roșie", "EN": "{r} of {n} valuation indicators in the red zone"},
    "dv.extra_title": {"RO": "🧮 Indicatori suplimentari", "EN": "🧮 Additional indicators"},
    "hist.hide_small": {"RO": "Începe graficul de la sume > {thr}", "EN": "Start chart at amounts > {thr}"},
}


def lang():
    return st.session_state.get("lang") or "RO"


def t(key, **kw):
    entry = _T.get(key)
    if entry is None:
        return key
    s = entry.get(lang()) or entry.get("RO") or key
    return s.format(**kw) if kw else s


_COLS = {
    "Nume": "Name", "Conturi": "Accounts", "Monedă": "Ccy", "Cant.": "Qty",
    "Preț mediu": "Avg price", "Preț curent": "Price", "Cost achiz.": "Cost",
    "Val. curentă": "Value", "P/L": "P/L", "Randament %": "Return %", "Div.": "Div.",
    "Div/Inv %": "Div/Inv %", "Rand. total %": "Total ret. %", "S&P500 %": "S&P500 %",
    "Zile": "Days", "PEG": "PEG", "vs S&P500 pp": "vs S&P500 pp", "Recomandare": "Analysts",
    "Scor TL": "TL score", "Rating": "Rating", "Scor risc": "Risk score",
}


_COLS_RO = {
    "Monedă": "Mon.", "Preț mediu": "Preț med.", "Preț curent": "Preț crt.",
    "Cost achiz.": "Cost Ach", "Val. curentă": "Val Crt.", "Randament %": "Rand%",
    "Recomandare": "Reco",
}


def col(name):
    """Eticheta afisata pentru o coloana; numele intern ramane in romana."""
    m = re.match(r"^(.*?)( \(.+\))$", name)
    base, suffix = (m.group(1), m.group(2)) if m else (name, "")
    if lang() != "EN":
        return _COLS_RO.get(base, base) + suffix
    return _COLS.get(base, base) + suffix


_PHRASES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "i18n_phrases.json")
_phrases = {}
_phrases_mtime = None


def _load_phrases():
    global _phrases, _phrases_mtime
    try:
        m = os.path.getmtime(_PHRASES_FILE)
    except OSError:
        return
    if m != _phrases_mtime:
        try:
            with open(_PHRASES_FILE, encoding="utf-8") as f:
                _phrases = json.load(f)
            _phrases_mtime = m
        except Exception:
            pass


def _x_exact(text):
    """Traduce un text static romanesc in EN daca exista in dictionar; altfel il lasa neschimbat."""
    if not isinstance(text, str) or lang() != "EN":
        return text
    _load_phrases()
    return _phrases.get(text, text)


_DISPLAY = (
    "metric", "subheader", "header", "title", "caption", "markdown", "info", "warning", "error",
    "success", "expander", "button", "selectbox", "number_input", "text_input", "text_area",
    "checkbox", "radio", "toggle", "download_button",
)
_KW = ("help", "label", "placeholder")


def install_translation():
    """Inlocuieste metodele de afisare Streamlit cu variante care traduc textele statice RO -> EN."""
    from streamlit.delta_generator import DeltaGenerator

    if getattr(DeltaGenerator, "_i18n_patched", False):
        return

    def wrap(orig, name):
        def inner(self, *args, **kwargs):
            if lang() == "EN":
                if args:
                    args = (x(args[0]),) + tuple(args[1:])
                if name == "metric":
                    if len(args) > 2:
                        args = args[:2] + (x(args[2]),) + tuple(args[3:])
                    if "delta" in kwargs:
                        kwargs["delta"] = x(kwargs["delta"])
                for k in _KW:
                    if k in kwargs:
                        kwargs[k] = x(kwargs[k])
            return orig(self, *args, **kwargs)

        inner.__name__ = getattr(orig, "__name__", "inner")
        inner.__doc__ = getattr(orig, "__doc__", None)
        return inner

    for name in _DISPLAY:
        orig = getattr(DeltaGenerator, name, None)
        if orig is not None:
            setattr(DeltaGenerator, name, wrap(orig, name))
    DeltaGenerator._i18n_patched = True
    main = getattr(st, "_main", None)
    if main is not None:
        for name in _DISPLAY:
            if hasattr(st, name) and hasattr(main, name):
                setattr(st, name, getattr(main, name))


_PATTERNS = [
    (r"Următorul dividend estimat: \*\*(.+?)\*\* \(data ex-dividend: (.+?)\)",
     r"Next estimated dividend: **\1** (ex-dividend date: \2)"),
    (r"P/E \(([\d.]+)\) sub 15 — reper generic de valuation scăzută\.",
     r"P/E (\1) below 15 — generic low-valuation benchmark."),
    (r"P/E \(([\d.]+)\) peste 30 — reper generic de valuation ridicată\.",
     r"P/E (\1) above 30 — generic high-valuation benchmark."),
    (r"PEG \(([\d.]+)\) sub 1 — creșterea ar putea justifica valuation-ul\.",
     r"PEG (\1) below 1 — growth could justify the valuation."),
    (r"PEG \(([\d.]+)\) peste 2 — scump relativ la creșterea estimată\.",
     r"PEG (\1) above 2 — expensive relative to estimated growth."),
    (r"RSI \((\d+)\) în zonă de supracumpărare\.",
     r"RSI (\1) in overbought territory."),
    (r"RSI \((\d+)\) în zonă de supravânzare — posibil rebound tehnic\.",
     r"RSI (\1) in oversold territory — possible technical rebound."),
    (r"Dividend yield generos \(([\d.]+)%\) — verifică sustenabilitatea lui\.",
     r"Generous dividend yield (\1%) — check its sustainability."),
    (r"ROE \(([\d.]+)%\) peste 15% — reper generic de eficiență solidă a capitalului propriu\.",
     r"ROE (\1%) above 15% — generic benchmark of solid equity efficiency."),
]


def x(text):
    out = _x_exact(text)
    if lang() == "EN" and isinstance(out, str) and out == text:
        for pat, rep in _PATTERNS:
            out = re.sub(pat, rep, out)
    return out


_PATTERNS2 = [
    (r"Valoare firmă \(capitalizare \+ datorii - cash\) / EBITDA\. Compară companii cu structuri de capital diferite mai corect decât P/E \(reper uzual sector: (.+?)\)\.",
     r"Enterprise value (market cap + debt - cash) / EBITDA. Compares companies with different capital structures more fairly than P/E (typical sector benchmark: \1)."),
    (r"\(reper uzual sector, aproximativ: (.+?)\)\.",
     r"(typical sector benchmark, approx.: \1)."),
    (r"Rânduri roșii: (\d+); galbene: (\d+)\.",
     r"Red rows: \1; yellow rows: \2."),
]
_PATTERNS.extend(_PATTERNS2)


_PATTERNS3 = [
    (r"Preț / vânzări pe acțiune\. Util mai ales pentru companii încă neprofitabile, unde P/E nu are sens ",
     r"Price / sales per share. Mostly useful for still-unprofitable companies, where P/E makes no sense "),
    (r"Calculat pe (\d+)% din ponderi\.",
     r"Calculated on \1% of the weights."),
]
_PATTERNS.extend(_PATTERNS3)


_PATTERNS4 = [
    (r"Preț / profit pe acțiune din ultimele 12 luni\. Arată de câți ani de profit curent ai nevoie ca să-ți recuperezi investiția\.",
     r"Price / earnings per share over the last 12 months. Shows how many years of current profit you need to recover your investment."),
    (r"Preț / valoare contabilă pe acțiune\. Sub 1 poate însemna preț sub 'valoarea din carte'\.",
     r"Price / book value per share. Below 1 can mean a price below 'book value'."),
    (r" Reper uzual sector \(aproximativ, static\): (.+?)\.",
     r" Typical sector benchmark (approximate, static): \1."),
]
_PATTERNS.extend(_PATTERNS4)


_PATTERNS5 = [
    (r"(\d+)/100 \(mai mare = mai sigur\)", r"\1/100 (higher = safer)"),
    (r"(\d+)/100 \((.*?)\)", lambda m: "%s/100 (%s)" % (m.group(1), _x_exact(m.group(2)))),
    (r"(\d+) din (\d+) indicatori în zona roșie", r"\1 of \2 indicators in the red zone"),
    (r"Pondere în portofoliu după cumpărare: ([\d.]+)%", r"Portfolio weight after purchase: \1%"),
    (r"Semafoarele sunt reguli generale, nu un verdict; verde peste tot nu înseamnă „cumpără”\.",
     r"The traffic lights are general rules, not a verdict; all green does not mean “buy”."),
    (r"Sumă ipotetică de cumpărat \(în (\w+)\)", r"Hypothetical amount to buy (in \1)"),
    (r"\bCalitate:", "Quality:"),
    (r"\bRisc:", "Risk:"),
    (r"\bValuare:", "Valuation:"),
    (r"Evoluție recentă:", "Recent performance:"),
    (r"Mărimea poziției:", "Position size:"),
]
_PATTERNS.extend(_PATTERNS5)


_PATTERNS6 = [
    (r"(-?\d+)% față de maxim", r"\1% from the high"),
    (r"\bsub SMA200\b", "below SMA200"),
    (r"\+(\d+)% în 3 luni", r"+\1% in 3 months"),
]
_PATTERNS.extend(_PATTERNS6)


_PATTERNS7 = [
    (r"\bCalitate\b(?=\**:)", "Quality"),
    (r"\bRisc\b(?=\**:)", "Risk"),
    (r"\bValuare\b(?=\**:)", "Valuation"),
    (r"Evoluție recentă(?=\**:)", "Recent performance"),
    (r"Mărimea poziției(?=\**:)", "Position size"),
    (r"fără semnale de alarmă", "no alarm signals"),
    (r"\b(Excelent|Aprobat|Vulnerabil|Respins)\b", lambda m: _x_exact(m.group(1))),
]
_PATTERNS.extend(_PATTERNS7)


_PATTERNS8 = [
    (r"din care efect de curs: ([+-][\d.]+) pp", r"of which FX effect: \1 pp"),
]
_PATTERNS.extend(_PATTERNS8)


_PATTERNS9 = [
    (r"Total Investit \((\w+)\)", r"Total Invested (\1)"),
    (r"Valoare de Piață \((\w+)\)", r"Market Value (\1)"),
    (r"Total Dividende Încasate \((\w+)\)", r"Total Dividends Received (\1)"),
]
_PATTERNS.extend(_PATTERNS9)
