"""Coloanele calculate ale pozitiilor de pe pagina principala (fara UI): valori, randament, dividende, scoruri."""
import pandas as pd

from core import days_held_from_iso
from t212_api import fetch_fx_rate

# coloanele pe care le foloseste pagina principala din pozitiile Trading 212 (tabel gol cand lipsesc)
T212_POSITION_COLUMNS = {"ticker": "object", "quantity": "float64", "averagePrice": "float64",
                         "currentPrice": "float64", "ppl": "float64", "initialFillDate": "object"}


def div_score(entry):
    entry = entry or {}
    if entry.get("div_total") is None or (entry.get("div_coverage") or 0) < 50:
        return None
    return round(entry["div_total"], 1)


def _score(entry, total_key, coverage_key=None):
    if entry.get(total_key) is None:
        return None
    if coverage_key and (entry.get(coverage_key) or 0) < 50:
        return None
    return round(entry.get(total_key), 1)


def build_t212_frame(positions, instruments, instruments_error, account_currency, dividends, ratings, quality_data):
    """Pozitiile Trading 212 cu valori, randament, dividende si scoruri.
    Intoarce (df, fx_errors, total_portfolio_value, total_dividende)."""
    if positions:
        df = pd.DataFrame(positions)
    else:
        df = pd.DataFrame({c: pd.Series(dtype=dt) for c, dt in T212_POSITION_COLUMNS.items()})

    if instruments_error or not instruments:
        df["name"] = df["ticker"]
        df["currencyCode"] = ""
    else:
        meta = pd.DataFrame(instruments)[["ticker", "name", "currencyCode"]]
        df = df.merge(meta, on="ticker", how="left")
        df["name"] = df["name"].fillna(df["ticker"])
        df["currencyCode"] = df["currencyCode"].fillna("")

    # GBX (penny sterling, LSE) nu e o monedă reală — o transformăm în GBP peste tot (1 GBP = 100 GBX)
    # înainte de orice alt calcul, ca prețurile/costurile afișate să fie mereu într-o monedă reală.
    gbx_mask = df["currencyCode"] == "GBX"
    df.loc[gbx_mask, "averagePrice"] = df.loc[gbx_mask, "averagePrice"] / 100
    df.loc[gbx_mask, "currentPrice"] = df.loc[gbx_mask, "currentPrice"] / 100
    df.loc[gbx_mask, "currencyCode"] = "GBP"

    df["valoare_curenta"] = df["quantity"] * df["currentPrice"]
    df["cost_achizitie"] = df["quantity"] * df["averagePrice"]

    # Randament = (Preț curent / Preț mediu − 1) × 100 — pur din preț, în moneda instrumentului,
    # fără nicio conversie valutară (nu depinde de moneda contului).
    df["randament_%"] = ((df["currentPrice"] / df["averagePrice"] - 1) * 100).round(2)

    # Pentru "Dividende / bani investiți" tot avem nevoie de costul de achiziție convertit în
    # moneda contului, pentru că dividendele vin în moneda contului, nu în cea a instrumentului.
    fx_errors = []
    fx_rates = {}
    for ccy in [c for c in df["currencyCode"].unique() if c]:
        rate, fx_err = fetch_fx_rate(ccy, account_currency)
        fx_rates[ccy] = rate
        if fx_err:
            fx_errors.append(fx_err)
    df["fx_rate"] = pd.to_numeric(df["currencyCode"].map(fx_rates).fillna(1.0))
    total_portfolio_value = (df["valoare_curenta"] * df["fx_rate"]).sum()
    df["cost_achizitie_cont"] = df["cost_achizitie"] * df["fx_rate"]

    df["dividende_incasate"] = pd.to_numeric(df["ticker"].map(lambda t: dividends.get(t, {}).get("total", 0.0)))
    df["div_pe_investit_%"] = (df["dividende_incasate"] / df["cost_achizitie_cont"] * 100).round(2)
    df["randament_total_%"] = (df["randament_%"] + df["div_pe_investit_%"]).round(2)
    total_dividende = df["dividende_incasate"].sum()

    df["recomandare"] = df["ticker"].map(lambda t: ratings.get(t, "none"))
    df["Scor"] = df["ticker"].map(lambda t: _score(quality_data.get(t, {}), "total"))
    df["Rating"] = df["ticker"].map(lambda t: quality_data.get(t, {}).get("rating"))
    df["Scor risc"] = df["ticker"].map(lambda t: _score(quality_data.get(t, {}), "risk_total"))
    df["Scor div."] = df["ticker"].map(lambda t: div_score(quality_data.get(t)))
    return df, fx_errors, total_portfolio_value, total_dividende


def finish_t212_frame(df, mc):
    """Sortare dupa nume, zile detinute si comparatia cu S&P 500 (mc = contextul de piata din cache)."""
    df = df.sort_values("name", key=lambda c: c.astype(str).str.casefold(), ascending=True).reset_index(drop=True)
    df["zile_detinut"] = df["initialFillDate"].apply(days_held_from_iso) if "initialFillDate" in df.columns else None
    df["sp500_return_%"] = df["ticker"].map(lambda t: mc.get(t, {}).get("sp500_return_%"))
    df["peg_ratio_display"] = df["ticker"].map(lambda t: mc.get(t, {}).get("peg"))
    df["sp500_return_%"] = pd.to_numeric(df["sp500_return_%"], errors="coerce")
    df["alpha_%"] = pd.to_numeric(df["randament_total_%"], errors="coerce") - df["sp500_return_%"]
    return df


def enrich_view(vdf, ratings, targets, quality_data, mc):
    """Coloanele de recomandari, scoruri si S&P 500 pentru randurile afisate (toate portofoliile alese)."""
    vdf = vdf.copy()
    vdf["recomandare"] = vdf["ticker"].map(lambda t: ratings.get(t, "none"))
    vdf["tinta_%"] = vdf["ticker"].map(lambda t: (targets.get(t) or {}).get("upside"))
    vdf["Scor"] = vdf["ticker"].map(lambda t: _score(quality_data.get(t, {}), "total", "coverage"))
    vdf["Rating"] = vdf["ticker"].map(lambda t: quality_data.get(t, {}).get("rating"))
    vdf["Scor risc"] = vdf["ticker"].map(lambda t: _score(quality_data.get(t, {}), "risk_total", "risk_coverage"))
    vdf["Scor div."] = vdf["ticker"].map(lambda t: div_score(quality_data.get(t)))
    vdf["sp500_return_%"] = pd.to_numeric(vdf["ticker"].map(lambda t: mc.get(t, {}).get("sp500_return_%")), errors="coerce")
    vdf["peg_ratio_display"] = vdf["ticker"].map(lambda t: mc.get(t, {}).get("peg"))
    vdf["alpha_%"] = pd.to_numeric(vdf["randament_total_%"], errors="coerce") - vdf["sp500_return_%"]
    vdf["zile_detinut"] = vdf["initialFillDate"].apply(days_held_from_iso) if "initialFillDate" in vdf.columns else None
    return vdf
