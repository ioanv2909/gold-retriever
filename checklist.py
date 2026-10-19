CHECKLIST_THRESHOLDS = {
    "quality_green": 65,
    "quality_yellow": 50,
    "risk_green": 75,
    "risk_yellow": 50,
    "valuation_yellow_ratio": 0.5,
    "min_valuation_indicators": 3,
    "trend_drawdown": 25,
    "trend_fast_run": 40,
    "weight_green": 5,
    "weight_yellow": 10,
    "min_coverage": 50,
}


def build_checklist(
    quality_total=None,
    quality_coverage=None,
    quality_rating=None,
    risk_total=None,
    risk_coverage=None,
    valuation_red=None,
    valuation_usable=None,
    drawdown_52w=None,
    price=None,
    sma200=None,
    ret_3m=None,
    weight_after=None,
    is_etf=False,
) -> dict:
    rows = []

    if quality_total is None or quality_coverage is None or quality_coverage < CHECKLIST_THRESHOLDS["min_coverage"]:
        rows.append(
            {
                "key": "quality",
                "label": "Calitate",
                "status": "grey",
                "detail": "Date insuficiente",
            }
        )
    else:
        if quality_total >= CHECKLIST_THRESHOLDS["quality_green"]:
            status = "green"
        elif quality_total >= CHECKLIST_THRESHOLDS["quality_yellow"]:
            status = "yellow"
        else:
            status = "red"

        detail = f"Scor {quality_total:.0f}"
        if quality_rating:
            detail += f" ({quality_rating})"

        rows.append(
            {
                "key": "quality",
                "label": "Calitate",
                "status": status,
                "detail": detail,
            }
        )

    if risk_total is None or risk_coverage is None or risk_coverage < CHECKLIST_THRESHOLDS["min_coverage"]:
        rows.append(
            {
                "key": "risk",
                "label": "Risc",
                "status": "grey",
                "detail": "Date insuficiente",
            }
        )
    else:
        if risk_total >= CHECKLIST_THRESHOLDS["risk_green"]:
            status = "green"
        elif risk_total >= CHECKLIST_THRESHOLDS["risk_yellow"]:
            status = "yellow"
        else:
            status = "red"

        rows.append(
            {
                "key": "risk",
                "label": "Risc",
                "status": status,
                "detail": f"Scor risc {risk_total:.0f} (mai mare = mai sigur)",
            }
        )

    if is_etf:
        rows.append(
            {
                "key": "valuation",
                "label": "Valuare",
                "status": "grey",
                "detail": "Nu se aplică la ETF-uri",
            }
        )
    elif valuation_usable is None or valuation_usable < CHECKLIST_THRESHOLDS["min_valuation_indicators"] or valuation_red is None:
        rows.append(
            {
                "key": "valuation",
                "label": "Valuare",
                "status": "grey",
                "detail": "Date insuficiente",
            }
        )
    else:
        if valuation_red == 0:
            status = "green"
        elif valuation_red / valuation_usable <= CHECKLIST_THRESHOLDS["valuation_yellow_ratio"]:
            status = "yellow"
        else:
            status = "red"

        rows.append(
            {
                "key": "valuation",
                "label": "Valuare",
                "status": status,
                "detail": f"{valuation_red} din {valuation_usable} indicatori în zona roșie",
            }
        )

    deep = drawdown_52w is not None and drawdown_52w <= -CHECKLIST_THRESHOLDS["trend_drawdown"]
    below = price is not None and sma200 is not None and price < sma200
    fast = ret_3m is not None and ret_3m > CHECKLIST_THRESHOLDS["trend_fast_run"]
    has_trend_data = (
        drawdown_52w is not None
        or (price is not None and sma200 is not None)
        or ret_3m is not None
    )

    if not has_trend_data:
        rows.append(
            {
                "key": "trend",
                "label": "Evoluție recentă",
                "status": "grey",
                "detail": "Date insuficiente",
            }
        )
    else:
        reasons = []
        if deep:
            reasons.append(f"{drawdown_52w:.0f}% față de maxim")
        if below:
            reasons.append("sub SMA200")
        if fast:
            reasons.append(f"+{ret_3m:.0f}% în 3 luni")

        if deep and below:
            status = "red"
        elif deep or below or fast:
            status = "yellow"
        else:
            status = "green"

        rows.append(
            {
                "key": "trend",
                "label": "Evoluție recentă",
                "status": status,
                "detail": "; ".join(reasons) if reasons else "fără semnale de alarmă",
            }
        )

    if weight_after is None:
        rows.append(
            {
                "key": "weight",
                "label": "Mărimea poziției",
                "status": "grey",
                "detail": "Introdu o sumă ipotetică",
            }
        )
    else:
        if weight_after <= CHECKLIST_THRESHOLDS["weight_green"]:
            status = "green"
        elif weight_after <= CHECKLIST_THRESHOLDS["weight_yellow"]:
            status = "yellow"
        else:
            status = "red"

        rows.append(
            {
                "key": "weight",
                "label": "Mărimea poziției",
                "status": status,
                "detail": f"Pondere în portofoliu după cumpărare: {weight_after:.1f}%",
            }
        )

    counts = {"green": 0, "yellow": 0, "red": 0, "grey": 0}
    for row in rows:
        counts[row["status"]] += 1

    return {"rows": rows, "counts": counts}
