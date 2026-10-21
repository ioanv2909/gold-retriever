import checklist


def _text(**kw):
    return repr(checklist.build_checklist(**kw))


def test_quality_and_risk_are_shown_out_of_100():
    text = _text(quality_total=25, quality_coverage=100, quality_rating="Respins",
                 risk_total=9, risk_coverage=100)
    assert "25/100 (Respins)" in text
    assert "9/100 (mai mare = mai sigur)" in text


def test_scores_are_rounded_to_whole_numbers():
    text = _text(quality_total=64.6, quality_coverage=100, quality_rating="Bun",
                 risk_total=74.4, risk_coverage=100)
    assert "65/100 (Bun)" in text
    assert "74/100 (mai mare = mai sigur)" in text


def test_missing_data_is_not_shown_as_a_score():
    text = _text(quality_total=None, risk_total=None)
    assert "/100" not in text
    assert "Date insuficiente" in text
