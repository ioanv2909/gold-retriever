import numpy as np
import pandas as pd


RISK_INDICATORS = [
    {
        "key": "volatility",
        "label": "Volatilitate anualizată (%)",
        "weight": 30,
        "target": 20,
        "red_flag": 50,
        "higher_is_better": False,
    },
    {
        "key": "max_drawdown",
        "label": "Drawdown maxim 3 ani (%)",
        "weight": 30,
        "target": 20,
        "red_flag": 50,
        "higher_is_better": False,
    },
    {
        "key": "beta",
        "label": "Beta",
        "weight": 10,
        "target": 1.0,
        "red_flag": 1.8,
        "higher_is_better": False,
    },
    {
        "key": "net_debt_ebitda",
        "label": "Net Debt / EBITDA (x)",
        "weight": 15,
        "target": 2,
        "red_flag": 4,
        "higher_is_better": False,
    },
    {
        "key": "interest_coverage",
        "label": "Interest Coverage (x)",
        "weight": 15,
        "target": 8,
        "red_flag": 3,
        "higher_is_better": True,
    },
]


def risk_indicator_score(value, target, red_flag, higher_is_better):
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


def clean_close(close, fund=False):
    cleaned = close.dropna().sort_index().astype(float).copy()
    notes = []

    if fund:
        for i in range(1, len(cleaned)):
            prev = cleaned.iloc[i - 1]
            curr = cleaned.iloc[i]

            if prev == 0 or not np.isfinite(prev) or not np.isfinite(curr):
                continue

            r = curr / prev
            if 0.6 <= r <= 1.7:
                continue

            k = max(r, 1 / r)
            rounded_k = round(k)
            if rounded_k >= 2 and abs(k - rounded_k) / rounded_k <= 0.03:
                cleaned.iloc[:i] = cleaned.iloc[:i] * r
                data = cleaned.index[i].date() if hasattr(cleaned.index[i], "date") else cleaned.index[i]
                notes.append(f"discontinuitate ~1:{rounded_k} la {data}")

    isolated_threshold = 0.08 if fund else 0.30
    drop_indexes = []
    for i in range(1, len(cleaned) - 1):
        prev = cleaned.iloc[i - 1]
        curr = cleaned.iloc[i]
        next_val = cleaned.iloc[i + 1]

        if prev == 0 or not np.isfinite(prev) or not np.isfinite(curr) or not np.isfinite(next_val):
            continue

        current_ratio = curr / prev
        next_ratio = next_val / prev

        if abs(current_ratio - 1) > isolated_threshold and 0.97 <= next_ratio <= 1.03:
            data = cleaned.index[i].date() if hasattr(cleaned.index[i], "date") else cleaned.index[i]
            drop_indexes.append(cleaned.index[i])
            notes.append(f"preț izolat eliminat la {data}")

    if drop_indexes:
        cleaned = cleaned.drop(index=drop_indexes)

    return cleaned, notes


def extract_risk_metrics(tk, quality_metrics=None):
    metrics = {ind["key"]: None for ind in RISK_INDICATORS}
    notes = {}

    try:
        history = tk.history(period="3y")
        close = history["Close"].dropna()

        try:
            fund = tk.info.get("quoteType") in ("ETF", "MUTUALFUND")
        except Exception:
            fund = False

        close, clean_notes = clean_close(close, fund=fund)
        if clean_notes:
            notes["price_clean"] = "; ".join(clean_notes)

        if len(close) >= 120:
            returns = close.pct_change().dropna()
            if not returns.empty:
                metrics["volatility"] = float(returns.std() * np.sqrt(252) * 100)

            drawdown = (close / close.cummax()) - 1
            if not drawdown.empty:
                metrics["max_drawdown"] = float(abs(drawdown.min()) * 100)

            notes["price_history"] = f"{len(close) / 252:.1f} ani"
    except Exception:
        metrics["volatility"] = None
        metrics["max_drawdown"] = None

    try:
        beta = tk.info.get("beta")
        if beta is not None and not pd.isna(beta):
            metrics["beta"] = float(beta)
    except Exception:
        metrics["beta"] = None

    if quality_metrics is not None:
        metrics["net_debt_ebitda"] = quality_metrics.get("net_debt_ebitda")
        metrics["interest_coverage"] = quality_metrics.get("interest_coverage")

    return metrics, notes


def compute_risk(metrics):
    rows = []
    total_points = 0.0
    coverage = 0.0

    for ind in RISK_INDICATORS:
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
            score = risk_indicator_score(val, target, red_flag, higher_is_better)
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

    total = float((total_points / coverage) * 100) if coverage > 0 else 0.0

    if coverage < 50:
        rating = "Date insuficiente"
    elif total >= 75:
        rating = "Risc scăzut"
    elif total >= 50:
        rating = "Moderat"
    elif total >= 25:
        rating = "Ridicat"
    else:
        rating = "Foarte ridicat"

    return {
        "rows": rows,
        "total": total,
        "coverage": coverage,
        "rating": rating,
    }
