"""Cautarea rapida de pozitii."""
import pandas as pd

import quick_search


def test_options_sorted_by_name_with_ticker_once():
    df = pd.DataFrame({"ticker": ["MSFT_US_EQ", "AAPL_US_EQ", "MSFT_US_EQ", "X"], "name": ["Microsoft", "Apple", "Microsoft", "X"]})
    assert quick_search.options(df) == [("AAPL_US_EQ", "Apple (AAPL_US_EQ)"), ("MSFT_US_EQ", "Microsoft (MSFT_US_EQ)"), ("X", "X")]
