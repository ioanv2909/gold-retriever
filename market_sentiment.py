"""CNN's US stock market sentiment indicator."""
import csv
from datetime import date
from io import StringIO

import requests
import streamlit as st

from i18n import t

_SOURCE = "https://www.cnn.com/markets/fear-and-greed"
_ARCHIVE = "https://raw.githubusercontent.com/whit3rabbit/fear-greed-data/main/datasets/cnn_fear_greed.csv"
_RATINGS = {"extreme fear", "fear", "neutral", "greed", "extreme greed"}


@st.cache_data(ttl=900, show_spinner=False)
def load_fear_and_greed():
    try:
        response = requests.get(_ARCHIVE, timeout=3)
        response.raise_for_status()
        rows = csv.DictReader(StringIO(response.text))
        latest = max(rows, key=lambda row: row["Date"], default=None)
        if latest is None:
            return None
        updated = date.fromisoformat(latest["Date"])
        score = float(latest["Fear Greed"])
        rating = latest["Rating"].strip().lower()
        if 0 <= score <= 100 and rating in _RATINGS:
            return score, rating, updated
    except (requests.RequestException, csv.Error, AttributeError, KeyError, TypeError, ValueError):
        pass
    return None


def render_fear_and_greed():
    reading = load_fear_and_greed()
    source = f"[CNN Fear & Greed Index]({_SOURCE})"
    if reading is None:
        st.caption(f"{source} · {t('fear_greed.unavailable')}")
        return

    score, rating, updated = reading
    sentiment = t(f"fear_greed.{rating}")
    reading_date = t("fear_greed.updated", date=updated.isoformat())
    st.html(f"""
        <style>
          .gr-fear-greed {{
            box-sizing: border-box;
            max-width: 30rem;
            padding: .75rem 1rem;
            border: 1px solid color-mix(in srgb, currentColor 20%, transparent);
            border-radius: .75rem;
            margin-bottom: .25rem;
          }}
          .gr-fear-greed-header, .gr-fear-greed-footer {{
            display: flex;
            justify-content: space-between;
            align-items: baseline;
            flex-wrap: wrap;
            gap: .25rem .75rem;
          }}
          .gr-fear-greed-header a {{ font-weight: 600; }}
          .gr-fear-greed-score {{ font-size: 1.35rem; font-weight: 700; line-height: 1; }}
          .gr-fear-greed-score small {{ font-size: .8rem; font-weight: 500; }}
          .gr-fear-greed-track {{
            position: relative;
            height: .55rem;
            margin: .7rem .25rem .5rem;
            border-radius: .35rem;
            background: linear-gradient(to right,
              #db555c 0% 25%, #e88b55 25% 45%, #e3bd58 45% 55%,
              #8cb978 55% 75%, #3c9b74 75% 100%);
          }}
          .gr-fear-greed-marker {{
            position: absolute;
            top: 50%;
            width: .85rem;
            height: .85rem;
            border: 2px solid currentColor;
            border-radius: 50%;
            background: var(--st-background-color, var(--background-color, #fff));
            transform: translate(-50%, -50%);
          }}
          .gr-fear-greed-footer {{ font-size: .8rem; }}
        </style>
        <div class="gr-fear-greed">
          <div class="gr-fear-greed-header">
            <a href="{_SOURCE}" target="_blank" rel="noopener noreferrer">CNN Fear &amp; Greed Index</a>
            <span class="gr-fear-greed-score">{score:.0f}<small> / 100</small></span>
          </div>
          <div class="gr-fear-greed-track" aria-hidden="true">
            <span class="gr-fear-greed-marker" style="left: {score:.2f}%"></span>
          </div>
          <div class="gr-fear-greed-footer">
            <strong>{sentiment}</strong><span>{reading_date}</span>
          </div>
        </div>
    """)
