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
    st.markdown(f"{source} · **{score:.0f}/100** · {sentiment} · {reading_date}")
