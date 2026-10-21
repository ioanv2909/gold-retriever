import pandas as pd
import pytest

import health
import signals
import strategies

NOW = pd.Timestamp("2026-10-21 12:00").timestamp()


@pytest.mark.parametrize("title, cat, tone", [
    ("Microsoft to acquire gaming studio in $2 billion deal", "m_and_a", 0),
    ("Apple shares plunge after EU antitrust probe", "regulation", -1),
    ("Nvidia beats estimates, raises guidance", "earnings", 1),
    ("Pfizer CEO steps down", "management", 0),
    ("Company wins patent lawsuit against rival", "legal", 0),
    ("Board approves $10 billion buyback", "capital", 1),
    ("Five stocks to watch this week", None, 0),
])
def test_classify_headline(title, cat, tone):
    assert signals.classify_headline(title) == (cat, tone)


def test_rating_stats_counts_last_90_days():
    df = pd.DataFrame({
        "Firm": ["A", "B", "C", "D", "E"],
        "FromGrade": ["Hold", "Buy", "Buy", "Buy", "Hold"],
        "ToGrade": ["Buy", "Hold", "Buy", "Buy", "Buy"],
        "Action": ["up", "down", "main", "reit", "up"],
        "priceTargetAction": ["Raises", "Lowers", "Raises", "Maintains", "Raises"],
    }, index=pd.to_datetime(["2026-10-01", "2026-09-15", "2026-08-01", "2026-10-10", "2026-03-01"]))
    r = signals.rating_stats(df, NOW)
    assert (r["upgrades"], r["downgrades"], r["raises"], r["lowers"]) == (1, 1, 2, 1)
    kinds = sorted((e["kind"], e["alert"]) for e in r["events"])
    assert kinds == [("downgrade", True), ("upgrade", False)]


def test_insider_stats_only_open_market_trades():
    df = pd.DataFrame({
        "Value": [1_000_000, 50_000_000, 0, 200_000, 9_000_000],
        "Text": ["Purchase at price 10.00 per share.", "Sale at price 500 per share.",
                 "Stock Award(Grant) at price 0.00 per share.", "Sale at price 20 per share.",
                 "Purchase at price 5 per share."],
        "Insider": ["X", "Y", "Z", "W", "OLD"], "Position": ["CEO", "CFO", "Director", "Officer", "CEO"],
        "Start Date": pd.to_datetime(["2026-09-01", "2026-08-01", "2026-09-01", "2026-10-01", "2025-01-01"]),
    })
    r = signals.insider_stats(df, 100_000_000_000, NOW)
    assert r["insider_buys"] == 1 and r["insider_sells"] == 2
    assert r["insider_net"] == pytest.approx((1_000_000 - 50_200_000) / 100_000_000_000 * 100)
    # vanzarea mica (0,0002% din capitalizare) nu intra in cronologie; cea de 0,05% da
    assert [e["kind"] for e in r["events"]] == ["insider_buy", "insider_sale"]
    assert signals.insider_stats(None, 1, NOW)["insider_net"] is None


def test_institutions_change_weighted():
    df = pd.DataFrame({"pctHeld": [0.08, 0.06, 0.02], "pctChange": [0.02, -0.01, 0.05]})
    assert signals.institutions_change(df) == pytest.approx((0.08 * 2 - 0.06 * 1 + 0.02 * 5) / 0.16)
    assert signals.institutions_change(df.head(2)) is None


def test_news_items_and_tone():
    raw = [{"title": "Stock soars on record results", "providerPublishTime": NOW - 86400, "link": "l1"},
           {"title": "Shares jump after upgrade", "providerPublishTime": NOW - 2 * 86400},
           {"title": "Company faces probe", "providerPublishTime": NOW - 3 * 86400},
           {"title": "Old news: shares fall", "providerPublishTime": NOW - 60 * 86400}]
    items = signals.news_items(raw, NOW)
    assert len(items) == 3 and items[0]["date"] == "2026-10-20"
    assert signals.news_tone(items) == pytest.approx((2 - 1) / 3 * 100)
    assert signals.news_tone(items[:2]) is None


def test_earnings_stats_reaction_before_and_after_close():
    tz = "America/New_York"
    earn = pd.DataFrame({
        "EPS Estimate": [1.0, 1.0, 1.0, 1.0, 1.0],
        "Reported EPS": [float("nan"), 1.1, 0.9, 1.2, 1.05],
        "Surprise(%)": [float("nan"), 10.0, -10.0, 20.0, 5.0],
    }, index=pd.DatetimeIndex(["2026-11-01 16:00", "2026-10-01 16:00", "2026-07-01 08:00", "2026-04-01 16:00",
                               "2026-01-05 16:00"]).tz_localize(tz))
    days = pd.bdate_range("2025-12-01", "2026-10-20", tz=tz)
    close = pd.Series(100.0, index=days)
    close[close.index >= pd.Timestamp("2026-10-02", tz=tz)] = 110.0   # dupa inchidere: +10% a doua zi
    close[(close.index >= pd.Timestamp("2026-07-01", tz=tz)) & (close.index < pd.Timestamp("2026-10-02", tz=tz))] = 95.0
    r = signals.earnings_stats(earn, close, NOW)
    assert r["earnings_n"] == 4 and r["beat_rate"] == 75.0 and r["avg_surprise"] == pytest.approx(6.25)
    # reactii: 1 oct dupa inchidere: 95 -> 110 a doua zi; 1 iul inainte de deschidere: 100 -> 95; apoi 0, 0
    assert r["avg_reaction"] == pytest.approx(((110 / 95 - 1) * 100 - 5.0) / 4)
    assert [e["date"] for e in r["events"]] == ["2026-10-01", "2026-07-01"]  # doar ultimele 180 de zile


def test_parse_8k_items_and_links():
    sub = {"filings": {"recent": {
        "form": ["8-K", "10-Q", "8-K", "8-K"],
        "filingDate": ["2026-10-01", "2026-09-01", "2026-08-01", "2025-01-01"],
        "accessionNumber": ["0001-26-000001", "x", "0001-26-000002", "0001-25-000003"],
        "primaryDocument": ["a.htm", "b.htm", "c.htm", "d.htm"],
        "items": ["5.02,9.01", "", "2.02,4.02", "2.01"],
    }}}
    ev = signals.parse_8k(sub, 789019, NOW)
    assert [(e["date"], e["kind"], e["tone"], e["alert"]) for e in ev] == [
        ("2026-10-01", "management", 0, True), ("2026-08-01", "restatement", -1, True)]
    assert ev[0]["link"] == "https://www.sec.gov/Archives/edgar/data/789019/000126000001/a.htm"


class Resp:
    def __init__(self, data, code=200):
        self.status_code, self._data = code, data

    def json(self):
        return self._data


def test_edgar_events_with_contact_header_and_ticker_cache():
    calls = []

    def get(url, headers, timeout):
        calls.append((url, headers["User-Agent"]))
        if url.endswith("company_tickers.json"):
            return Resp({"0": {"ticker": "BRK-B", "cik_str": 1067983}, "1": {"ticker": "MSFT", "cik_str": 789019}})
        return Resp({"filings": {"recent": {"form": ["8-K"], "filingDate": ["2026-10-01"],
                                             "accessionNumber": ["0001-26-1"], "primaryDocument": ["a.htm"],
                                             "items": ["1.03"]}}})

    ev = signals.edgar_events("MSFT", "admin@example.com", NOW, get)
    assert ev[0]["kind"] == "legal" and calls[0][1] == "GoldRetriever admin@example.com"
    assert calls[1][0] == "https://data.sec.gov/submissions/CIK0000789019.json"
    assert signals.sec_cik("BRK.B", "admin@example.com", NOW, get) == 1067983
    assert sum(1 for u, _ in calls if u.endswith("company_tickers.json")) == 1   # lista se tine local
    assert health.status("sec")["level"] == "green"
    assert signals.edgar_events("NOPE", "a@b.c", NOW, get) == []


def test_event_balance_ignores_ratings_and_earnings_and_old_events():
    ev = [signals._event("2026-10-01", "sec", "restatement", -1, "8-K 4.02"),
          signals._event("2026-10-02", "news", "m_and_a", 1, "x"),
          signals._event("2026-10-03", "insider", "insider_buy", 1, "y"),
          signals._event("2026-10-04", "rating", "downgrade", -1, "z"),
          signals._event("2026-10-05", "earnings", "earnings", 1, "w"),
          signals._event("2026-05-01", "sec", "impairment", -1, "old")]
    assert signals.event_balance(ev, NOW) == (1, 3)


class FakeTicker:
    info = {}
    upgrades_downgrades = pd.DataFrame({"Firm": ["A"], "FromGrade": ["Hold"], "ToGrade": ["Buy"], "Action": ["up"],
                                        "priceTargetAction": ["Raises"]}, index=pd.to_datetime(["2026-10-01"]))
    insider_transactions = None
    institutional_holders = None

    def history(self, period):
        raise RuntimeError("no prices")

    def get_earnings_dates(self, limit):
        return None


def test_extract_uses_sec_only_for_us_companies_with_contact():
    info = {"country": "United States", "marketCap": 1e9, "recommendationMean": 2.0, "numberOfAnalystOpinions": 10,
            "shortPercentOfFloat": 0.03, "sharesShort": 110, "sharesShortPriorMonth": 100}
    sec = [signals._event("2026-10-10", "sec", "management", 0, "8-K 5.02", alert=True)]
    news = [{"title": "Company to acquire rival, shares jump", "providerPublishTime": NOW - 3600, "link": "n"}]
    m = signals.extract(FakeTicker(), "XYZ", info, now=NOW, ua_email="a@b.c", news_fn=lambda s: news,
                        edgar_fn=lambda *a: sec)
    assert m["rating_net_90d"] == 1 and m["target_net_90d"] is None and m["rec_mean"] == 2.0
    assert m["short_float"] == pytest.approx(3.0) and m["short_change"] == pytest.approx(10.0)
    assert m["sec_checked"] and [e["source"] for e in m["events"]] == ["news", "sec", "rating"]
    assert (m["event_balance"], m["event_n"]) == (1, 2)
    eu = signals.extract(FakeTicker(), "SAP.DE", dict(info, country="Germany"), now=NOW, ua_email="a@b.c",
                         news_fn=lambda s: [], edgar_fn=lambda *a: sec)
    assert not eu["sec_checked"] and eu["event_balance"] is None
    nomail = signals.extract(FakeTicker(), "XYZ", info, now=NOW, ua_email=None, news_fn=lambda s: [],
                             edgar_fn=lambda *a: sec)
    assert not nomail["sec_checked"]


def test_sentiment_and_events_lenses():
    good = {"rating_net_90d": 3, "target_net_90d": 80, "eps_rev_90d": 4, "rec_mean": 1.6, "short_float": 1.0,
            "short_change": -20, "insider_net": 0.0, "inst_change": 3, "news_tone": 60}
    r = strategies.sentiment_lens(good)
    assert r["level"] == "strong" and r["coverage"] == 100
    bad = {"beat_rate": 25, "avg_surprise": -5, "avg_reaction": -4, "event_balance": -3}
    assert strategies.events_lens(bad)["level"] == "weak"
    assert strategies.events_lens({})["level"] == "insufficient"
    res = strategies.evaluate(dict(good, kind="stock"))
    assert set(res) == set(strategies.LENSES) and res["sentiment"]["level"] == "strong"


def test_market_text():
    from strategies_ui import _market_text
    assert _market_text({"vix": None, "spx_vs_sma200": None}) is None
    txt = _market_text({"vix": 28.0, "spx_vs_sma200": -4.2})
    assert "VIX 28.0 (agitat)" in txt and "-4.2%" in txt and "trend negativ" in txt


@pytest.mark.parametrize("title, cat", [
    ("3 Dividend Stocks to Buy and Hold Forever", None),
    ("Nvidia CEO Jensen Huang says AI demand is strong", None),
    ("Coca-Cola raises quarterly dividend for 64th year", "capital"),
    ("Intel names new CEO after Gelsinger steps down", "management"),
    ("Microsoft agrees to buy cybersecurity firm", "m_and_a"),
])
def test_classify_headline_ignores_generic_articles(title, cat):
    assert signals.classify_headline(title)[0] == cat


def test_news_items_keeps_only_related_articles():
    raw = [{"title": "a", "providerPublishTime": NOW, "relatedTickers": ["MSFT", "^GSPC"]},
           {"title": "b", "providerPublishTime": NOW, "relatedTickers": ["GOOGL"]},
           {"title": "c", "providerPublishTime": NOW}]
    assert [n["title"] for n in signals.news_items(raw, NOW, symbol="MSFT")] == ["a", "c"]
