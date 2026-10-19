import numpy as np
import pandas as pd


INDICATORS = [
    {
        "key": "roic",
        "label": "ROIC (%)",
        "weight": 20,
        "target": 15,
        "red_flag": 8,
        "higher_is_better": True,
    },
    {
        "key": "net_debt_ebitda",
        "label": "Net Debt / EBITDA (x)",
        "weight": 15,
        "target": 2.0,
        "red_flag": 4.0,
        "higher_is_better": False,
    },
    {
        "key": "rd_intensity",
        "label": "R&D Intensity (%)",
        "weight": 15,
        "target": 12,
        "red_flag": 5,
        "higher_is_better": True,
    },
    {
        "key": "gross_margin_trend",
        "label": "Gross Margin Trend (pp/an)",
        "weight": 15,
        "target": 0.0,
        "red_flag": -1.0,
        "higher_is_better": True,
    },
    {
        "key": "revenue_cagr",
        "label": "Revenue CAGR (%)",
        "weight": 10,
        "target": 8,
        "red_flag": 0,
        "higher_is_better": True,
    },
    {
        "key": "quality_of_earnings",
        "label": "FCF / Net Income (x)",
        "weight": 10,
        "target": 0.9,
        "red_flag": 0.7,
        "higher_is_better": True,
    },
    {
        "key": "share_count_change",
        "label": "Share Count Change (%/an)",
        "weight": 10,
        "target": 0,
        "red_flag": 3,
        "higher_is_better": False,
    },
    {
        "key": "interest_coverage",
        "label": "Interest Coverage (x)",
        "weight": 5,
        "target": 8,
        "red_flag": 3,
        "higher_is_better": True,
    },
]


def indicator_score(value, target, red_flag, higher_is_better):
    if value is None or pd.isna(value):
        return None
    if higher_is_better:
        if target == red_flag:
            return 1.0 if value >= target else 0.0
        score = (value - red_flag) / (target - red_flag)
    else:
        if red_flag == target:
            return 1.0 if value <= target else 0.0
        score = (red_flag - value) / (red_flag - target)
    return float(min(1.0, max(0.0, score)))


def safe_row(df, *names):
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return None
    for name in names:
        if name in df.index:
            row = df.loc[name]
            if isinstance(row, pd.DataFrame):
                row = row.iloc[0]
            return row
    return None


def extract_metrics(tk):
    metrics = {ind["key"]: None for ind in INDICATORS}
    notes = {}

    financials = getattr(tk, "financials", None)
    balance_sheet = getattr(tk, "balance_sheet", None)
    cashflow = getattr(tk, "cashflow", None)

    # 1. ROIC
    try:
        ebit_row = safe_row(financials, "EBIT", "Operating Income")
        debt_row = safe_row(balance_sheet, "Total Debt")
        equity_row = safe_row(
            balance_sheet,
            "Stockholders Equity",
            "Total Equity Gross Minority Interest",
            "Common Stock Equity",
        )
        cash_row = safe_row(
            balance_sheet,
            "Cash And Cash Equivalents",
            "Cash Cash Equivalents And Short Term Investments",
        )
        tax_rate_row = safe_row(financials, "Tax Rate For Calcs")

        if ebit_row is not None and debt_row is not None and equity_row is not None and cash_row is not None:
            ebit = ebit_row.dropna().iloc[0]
            debt = debt_row.dropna().iloc[0]
            equity = equity_row.dropna().iloc[0]
            cash = cash_row.dropna().iloc[0]

            tax_rate = 0.21
            if tax_rate_row is not None:
                valid_tax = tax_rate_row.dropna()
                if not valid_tax.empty:
                    tax_rate = float(valid_tax.iloc[0])

            nopat = ebit * (1 - tax_rate)
            invested_capital = debt + equity - cash
            if invested_capital > 0:
                metrics["roic"] = float((nopat / invested_capital) * 100)
    except Exception:
        metrics["roic"] = None

    # 2. Net Debt / EBITDA
    try:
        debt_row = safe_row(balance_sheet, "Total Debt")
        cash_row = safe_row(
            balance_sheet,
            "Cash And Cash Equivalents",
            "Cash Cash Equivalents And Short Term Investments",
        )
        ebitda_row = safe_row(financials, "EBITDA", "Normalized EBITDA")

        if debt_row is not None and cash_row is not None and ebitda_row is not None:
            ebitda = float(ebitda_row.dropna().iloc[0])
            if ebitda > 0:
                debt = float(debt_row.dropna().iloc[0])
                cash = float(cash_row.dropna().iloc[0])
                metrics["net_debt_ebitda"] = float((debt - cash) / ebitda)
    except Exception:
        metrics["net_debt_ebitda"] = None

    # 3. R&D Intensity
    try:
        rd_row = safe_row(financials, "Research And Development", "Research Development")
        rev_row = safe_row(financials, "Total Revenue", "Operating Revenue")

        if rd_row is not None and rev_row is not None:
            rd = rd_row.dropna().iloc[0]
            rev = rev_row.dropna().iloc[0]
            if rev and rev > 0 and pd.notna(rd):
                metrics["rd_intensity"] = float((rd / rev) * 100)
    except Exception:
        metrics["rd_intensity"] = None

    # 4. Gross Margin Trend
    try:
        gp_row = safe_row(financials, "Gross Profit")
        rev_row = safe_row(financials, "Total Revenue", "Operating Revenue")

        if gp_row is not None and rev_row is not None:
            df_gm = pd.DataFrame({"gp": gp_row, "rev": rev_row}).dropna()
            df_gm = df_gm[df_gm["rev"] > 0]
            if len(df_gm) >= 2:
                # Columns in financials are ordered newest to oldest
                margins = (df_gm["gp"] / df_gm["rev"]) * 100
                m_recent = margins.iloc[0]
                m_oldest = margins.iloc[-1]
                n_years = len(margins)
                metrics["gross_margin_trend"] = float((m_recent - m_oldest) / (n_years - 1))
                notes["gross_margin_trend"] = f"{n_years} ani"
    except Exception:
        metrics["gross_margin_trend"] = None

    # 5. Revenue CAGR
    try:
        rev_row = safe_row(financials, "Total Revenue", "Operating Revenue")
        if rev_row is not None:
            rev_series = rev_row.dropna()
            rev_series = rev_series[rev_series > 0]
            if len(rev_series) >= 2:
                rev_series = rev_series.iloc[:6]
                n_years = len(rev_series)
                rev_recent = rev_series.iloc[0]
                rev_old = rev_series.iloc[-1]
                metrics["revenue_cagr"] = float(((rev_recent / rev_old) ** (1 / (n_years - 1)) - 1) * 100)
                notes["revenue_cagr"] = f"{n_years} ani"
    except Exception:
        metrics["revenue_cagr"] = None

    # 6. Quality of Earnings
    try:
        fcf_row = safe_row(cashflow, "Free Cash Flow")
        net_inc_row = safe_row(financials, "Net Income", "Net Income Common Stockholders")

        if fcf_row is not None and net_inc_row is not None:
            fcf = float(fcf_row.dropna().iloc[0])
            net_income = float(net_inc_row.dropna().iloc[0])
            if net_income > 0:
                metrics["quality_of_earnings"] = float(fcf / net_income)
    except Exception:
        metrics["quality_of_earnings"] = None

    # 7. Share Count Change
    try:
        shares_row = safe_row(
            balance_sheet,
            "Ordinary Shares Number",
            "Share Issued",
            "Common Stock Shares Outstanding",
        )
        if shares_row is not None:
            shares = shares_row.dropna()
            shares = shares[shares > 0]
            if len(shares) >= 2:
                n_years = len(shares)
                shares_recent = shares.iloc[0]
                shares_old = shares.iloc[-1]
                metrics["share_count_change"] = float(((shares_recent / shares_old) ** (1 / (n_years - 1)) - 1) * 100)
                notes["share_count_change"] = f"{n_years} ani"
    except Exception:
        metrics["share_count_change"] = None

    # 8. Interest Coverage
    try:
        ebit_row = safe_row(financials, "EBIT", "Operating Income")
        interest_row = safe_row(financials, "Interest Expense", "Interest Expense Non Operating")

        if ebit_row is not None:
            ebit = float(ebit_row.dropna().iloc[0])
            if interest_row is None:
                metrics["interest_coverage"] = 999.0
            else:
                interest_series = interest_row.dropna()
                if interest_series.empty:
                    metrics["interest_coverage"] = 999.0
                else:
                    interest_exp = abs(float(interest_series.iloc[0]))
                    if interest_exp == 0:
                        metrics["interest_coverage"] = 999.0
                    else:
                        metrics["interest_coverage"] = float(ebit / interest_exp)
    except Exception:
        metrics["interest_coverage"] = None

    return metrics, notes


def compute_score(metrics):
    rows = []
    total_points = 0.0
    coverage = 0.0

    for ind in INDICATORS:
        key = ind["key"]
        val = metrics.get(key)
        weight = ind["weight"]
        target = ind["target"]
        red_flag = ind["red_flag"]
        higher_is_better = ind["higher_is_better"]

        if val is None or pd.isna(val):
            score = None
            points = None
        else:
            score = indicator_score(val, target, red_flag, higher_is_better)
            points = score * weight
            total_points += points
            coverage += weight

        rows.append({
            "key": key,
            "label": ind["label"],
            "value": val,
            "target": target,
            "red_flag": red_flag,
            "weight": weight,
            "score": score,
            "points": points,
        })

    if coverage < 50:
        total = float((total_points / coverage) * 100) if coverage > 0 else 0.0
        rating = "Date insuficiente"
    else:
        total = float((total_points / coverage) * 100)
        if total >= 80:
            rating = "Excelent"
        elif total >= 65:
            rating = "Aprobat"
        elif total >= 50:
            rating = "Vulnerabil"
        else:
            rating = "Respins"

    return {
        "rows": rows,
        "total": total,
        "coverage": coverage,
        "rating": rating,
    }
