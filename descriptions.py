"""Texte pentru tooltip-uri. Pragurile și ponderile se citesc din listele de configurare."""

DIRECTION = {True: "mai mare = mai bine", False: "mai mic = mai bine"}

_ND = ("În câți ani de profit operațional (EBITDA) ar putea plăti firma datoria netă. Zero sau negativ înseamnă mai mult numerar decât datorii.",
       "(Datorii totale − Numerar) / EBITDA; exclus dacă EBITDA ≤ 0.")
_IC = ("De câte ori profitul operațional acoperă dobânzile. Valoare mare = risc mic de insolvență.",
       "EBIT / |Cheltuieli cu dobânzile|; 999 dacă firma nu are dobânzi.")

WHAT = {
    "quality": {
        "roic": ("Rentabilitatea pe capitalul investit în afacere (datorii + capitaluri proprii, fără numerar). Peste costul capitalului înseamnă că firma creează valoare.",
                 "NOPAT / (Datorii totale + Capitaluri proprii − Numerar) × 100; NOPAT = EBIT × (1 − rata de taxare, 21% dacă nu e raportată)."),
        "net_debt_ebitda": _ND,
        "rd_intensity": ("Cât din venituri reinvestește firma în cercetare și dezvoltare. Contează în tech și farma; unde nu e raportată, indicatorul se exclude și scorul se renormalizează.",
                         "Cheltuieli R&D / Venituri totale × 100."),
        "gross_margin_trend": ("Dacă marja brută (puterea de preț) crește sau scade în timp.",
                               "(Marja brută cea mai recentă − cea mai veche) / (ani − 1), în puncte procentuale pe an; marja = Profit brut / Venituri."),
        "revenue_cagr": ("Ritmul anual compus de creștere a veniturilor.",
                         "((Venit recent / Venit vechi)^(1/(ani − 1)) − 1) × 100; yfinance dă de obicei 4 ani, deci 3 intervale."),
        "quality_of_earnings": ("Cât din profitul contabil se transformă în numerar real. Sub 1 = profitul depășește cash-ul generat.",
                                "Free Cash Flow / Profit net; exclus dacă profitul net ≤ 0."),
        "share_count_change": ("Diluarea sau răscumpărarea acțiunilor. Negativ = firma răscumpără, pozitiv = emite acțiuni noi.",
                               "Variația anualizată a numărului de acțiuni, în % pe an."),
        "interest_coverage": _IC,
    },
    "risk": {
        "volatility": ("Cât fluctuează prețul, anualizat. Mai mare = mișcări mai ample.",
                       "Abaterea standard a randamentelor zilnice pe ultimii 3 ani × √252 × 100."),
        "max_drawdown": ("Cea mai mare scădere de la un vârf la un minim ulterior în ultimii 3 ani: cât ai fi pierdut în cel mai rău moment.",
                         "|min(preț / maximul de până atunci − 1)| × 100, pe 3 ani."),
        "beta": ("Sensibilitatea față de piață: 1 = mișcare similară, peste 1 = mai agitat decât piața.",
                 "Beta raportat de Yahoo Finance (nu îl calculăm noi)."),
        "net_debt_ebitda": _ND,
        "interest_coverage": _IC,
    },
    "etf": {
        "ter": ("Costul anual al fondului, ca procent din investiție; se scade din randament în fiecare an.",
                "Total Expense Ratio din justETF (Yahoo ca rezervă), în % pe an."),
        "aum": ("Mărimea fondului. Fondurile mici au risc mai mare să fie închise.",
                "Dimensiunea fondului în milioane EUR (justETF)."),
        "age": ("Vechimea fondului: mai mult istoric, risc mai mic de închidere.",
                "Ani de la data lansării (justETF)."),
        "top10": ("Cât din fond e concentrat în primele 10 deținuri. La ETF-urile sectoriale concentrarea e mare prin definiție.",
                  "Suma ponderilor primelor 10 deținuri (Yahoo)."),
        "holdings": ("Numărul de poziții din fond: mai multe = diversificare mai mare.",
                     "Număr de deținuri din justETF; lipsește la ETC-uri."),
        "replication": ("Replicare fizică (fondul deține activele) sau sintetică (swap, cu risc de contraparte).",
                        "1 = replicare fizică, 0 = swap; din justETF."),
    },
    "valuation": {
        "pe": ("Prețul acțiunii față de profitul pe acțiune din ultimele 12 luni.",
               "Preț / EPS (TTM), de la Yahoo; exclus dacă ≤ 0 sau mai mare de 2× P/E forward (profit probabil distorsionat)."),
        "pe_fwd": ("Ca P/E trailing, dar cu profitul estimat pentru anul viitor.",
                   "Preț / EPS estimat (Yahoo); exclus dacă ≤ 0."),
        "peg": ("P/E raportat la creșterea estimată a profitului.",
                "PEG din Yahoo; exclus dacă ≤ 0."),
        "ev_ebitda": ("Valoarea firmei (capitalizare + datorii − numerar) raportată la profitul operațional EBITDA.",
                      "EV/EBITDA din Yahoo; exclus dacă ≤ 0."),
        "ps": ("Prețul raportat la vânzările pe acțiune.",
               "Preț / Vânzări (Yahoo); exclus dacă ≤ 0."),
        "pb": ("Prețul raportat la valoarea contabilă pe acțiune.",
               "Preț / Valoare contabilă (Yahoo); exclus dacă ≤ 0 sau dacă ROE > 40% (valoare contabilă golită de răscumpărări)."),
    },
}

SCORE_TEXT = {
    "quality": ("Scor de calitate pe termen lung (0–100) pentru acțiuni. Fiecare indicator primește un scor între 0 și 1 (1 la țintă sau mai bine, 0 la semnalul de alarmă sau mai rău, liniar între ele), înmulțit cu ponderea. Totalul se calculează doar pe indicatorii disponibili, renormalizat la 100.\n\n"
                "**Rating:** ≥ 80 Excelent / Core Buy, ≥ 65 Aprobat, ≥ 50 Vulnerabil, sub 50 Respins. Sub 50% din ponderi disponibile: Date insuficiente."),
    "risk": ("Scor de risc (0–100), mai mare = mai sigur. Calculat ca scorul de calitate, din volatilitate, drawdown maxim pe 3 ani, beta și indicatori de îndatorare; la ETF-uri doar partea de preț.\n\n"
             "**Rating:** ≥ 75 Risc scăzut, ≥ 50 Moderat, ≥ 25 Ridicat, sub 25 Foarte ridicat. Sub 50% din ponderi disponibile: Date insuficiente."),
    "etf": ("Scor ETF (0–100) pentru vehicul: cost, mărime, vechime, concentrare, număr de deținuri și replicare. Nu spune nimic despre piața urmărită.\n\n"
            "**Rating:** ≥ 80 Excelent, ≥ 65 Aprobat, ≥ 50 Vulnerabil, sub 50 Respins. Sub 50% din ponderi disponibile: Date insuficiente."),
}

_DEFAULT_THRESHOLDS = {
    "quality_green": 65, "quality_yellow": 50, "risk_green": 75, "risk_yellow": 50,
    "valuation_yellow_ratio": 0.5, "min_valuation_indicators": 3,
    "trend_drawdown": 25, "trend_fast_run": 40, "weight_green": 5, "weight_yellow": 10, "min_coverage": 50,
}

COLUMN_HELP = {
    "Scor TL": "Scor de calitate pe termen lung (0–100): la acțiuni, 8 indicatori financiari; la ETF-uri, scorul ETF. Detaliile și pragurile sunt în pagina poziției.",
    "Rating": "Eticheta scorului TL: ≥ 80 Excelent, ≥ 65 Aprobat, ≥ 50 Vulnerabil, sub 50 Respins; Date insuficiente dacă sunt sub 50% din ponderi.",
    "Scor risc": "Scor de risc (0–100), mai mare = mai sigur: volatilitate, drawdown maxim pe 3 ani, beta, îndatorare.",
    "Rating TL": "Eticheta scorului de calitate (sau a scorului ETF).",
    "Rating risc": "Eticheta scorului de risc: ≥ 75 Risc scăzut, ≥ 50 Moderat, ≥ 25 Ridicat, sub 25 Foarte ridicat.",
    "Recomandare": "Recomandarea de consens a analiștilor, din Yahoo Finance.",
    "Randament %": "(Preț curent / Preț mediu − 1) × 100, în moneda instrumentului.",
    "Rand. total %": "Randament de preț + dividendele încasate raportate la costul de achiziție.",
    "Div/Inv %": "Dividendele încasate raportate la costul de achiziție (yield on cost).",
    "S&P500 %": "Randamentul total al S&P 500 (^SP500TR, cu dividende reinvestite) pe aceeași perioadă de deținere ca poziția.",
    "vs S&P500 pp": "Randamentul total al poziției minus cel al S&P 500, în puncte procentuale.",
    "PEG": "P/E împărțit la creșterea estimată a profitului; sub 1 = potențial subevaluată relativ la creștere.",
    "Zile": "Zile de la prima achiziție.",
}

TABLE_HELP = {
    "Indicator": "Numele indicatorului.",
    "Valoare": "Valoarea calculată acum.",
    "Target": "Valoarea de la care indicatorul primește scor maxim (1,0).",
    "Red Flag": "Valoarea la care scorul devine 0.",
    "Pondere": "Cât contează indicatorul în scorul total.",
    "Scor (0-1)": "Scor intermediar: 1 la țintă, 0 la semnalul de alarmă, liniar între ele.",
    "Puncte": "Scor × pondere; suma punctelor, renormalizată pe ponderile disponibile, dă scorul total.",
}


def _fmt(x):
    return f"{x:g}"


def _config(kind):
    if kind == "quality":
        from scoring import INDICATORS as cfg
    elif kind == "risk":
        from risk import RISK_INDICATORS as cfg
    elif kind == "etf":
        from etf import ETF_INDICATORS as cfg
    elif kind == "valuation":
        from valuation import VALUATION_INDICATORS as cfg
    else:
        return []
    return cfg


def indicator_tooltip(kind, key):
    entry = WHAT.get(kind, {}).get(key) or WHAT["quality"].get(key) or ("", "")
    what, formula = entry
    cfg = next((c for c in _config(kind) if c.get("key") == key), None)
    parts = []
    if what:
        parts.append(what)
    if formula:
        parts.append("**Cum se calculează:** " + formula)
    if cfg:
        direction = DIRECTION[bool(cfg.get("higher_is_better", False))]
        if kind == "valuation":
            parts.append(f"**Prag:** zona roșie (semnal de alarmă) începe de la {_fmt(cfg['red_flag'])}; reper: {_fmt(cfg['target'])} ({direction}). Pragurile sunt generale, nu pe sector.")
        else:
            line = f"**Praguri:** scor maxim la {_fmt(cfg['target'])} sau mai bine, scor 0 la {_fmt(cfg['red_flag'])} sau mai rău ({direction})."
            if cfg.get("weight"):
                line += f" Pondere în scorul total: {_fmt(cfg['weight'])}%."
            parts.append(line)
    return "\n\n".join(parts)


def score_tooltip(kind):
    text = SCORE_TEXT.get(kind, "")
    cfg = _config(kind)
    weights = ", ".join(f"{c['label']} {_fmt(c['weight'])}" for c in cfg if c.get("weight"))
    if weights:
        text += f"\n\n**Ponderi:** {weights}."
    return text


def _thresholds():
    try:
        from checklist import CHECKLIST_THRESHOLDS
        return {**_DEFAULT_THRESHOLDS, **CHECKLIST_THRESHOLDS}
    except Exception:
        return dict(_DEFAULT_THRESHOLDS)


def checklist_tooltip(key):
    t = _thresholds()
    texts = {
        "quality": f"Verde: scor de calitate ≥ {t['quality_green']}; galben: ≥ {t['quality_yellow']}; roșu: sub. Gri: date insuficiente (sub {t['min_coverage']}% din ponderi).",
        "risk": f"Verde: scor de risc ≥ {t['risk_green']} (mai mare = mai sigur); galben: ≥ {t['risk_yellow']}; roșu: sub. Gri: date insuficiente.",
        "valuation": f"Verde: niciun indicator de valuare în zona roșie; galben: până la {int(t['valuation_yellow_ratio'] * 100)}% dintre cei utilizabili; roșu: peste. Gri: sub {t['min_valuation_indicators']} indicatori utilizabili sau ETF.",
        "trend": f"Roșu: scădere de cel puțin {t['trend_drawdown']}% față de maximul de 52 de săptămâni ȘI preț sub SMA200; galben: doar una dintre ele sau creștere de peste {t['trend_fast_run']}% în 3 luni; verde: fără semnale.",
        "weight": f"Ponderea poziției în portofoliul țintă ales, după cumpărarea ipotetică, față de valoarea pozițiilor lui (fără cash): verde ≤ {t['weight_green']}%, galben ≤ {t['weight_yellow']}%, roșu peste.",
    }
    return texts.get(key, "")
