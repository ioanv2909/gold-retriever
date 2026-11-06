import notice


def test_card_escapes_and_keeps_bold_and_code():
    h = notice.card_html("**Atenție** <b>x</b> `yfinance`\nrând 2")
    assert "<b>Atenție</b>" in h and "&lt;b&gt;x&lt;/b&gt;" in h
    assert "<code>yfinance</code>" in h and "<br>rând 2" in h
    assert "rgba(34,184,207,0.22)" in h and "#22b8cf" in h
