import history_ui


def test_chart_starts_with_value_and_invested():
    assert history_ui.DEFAULT_LINES == ("value", "invested")
    assert set(history_ui.DEFAULT_LINES) <= set(history_ui.LINES)
