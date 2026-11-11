from datetime import date
import pandas as pd
from streamlit.testing.v1 import AppTest
import value_quality as vq
import value_quality_ui as ui
from test_value_quality import ticker


def page():
    import pandas as pd
    from value_quality_ui import render_value_quality
    render_value_quality(pd.DataFrame(columns=['ticker','name']))


def test_no_data_fetch_on_open_and_manual_symbols_work_without_portfolio(monkeypatch):
    calls=[]
    def fetch(symbol):
        calls.append(symbol)
        return vq.extract_metrics(ticker(),'FIX',date(2026,11,11)) | {'symbol':symbol}
    monkeypatch.setattr(ui,'fetch_metrics',fetch)
    at=AppTest.from_function(page).run()
    assert not at.exception and calls==[]
    at.checkbox(key='vq_portfolio').uncheck()
    at.checkbox(key='vq_watchlist').uncheck()
    at.text_area(key='vq_manual').set_value('FIX, TEST')
    at.button(key='vq_run').click().run()
    assert not at.exception and calls==['FIX','TEST']
    assert any('Candidată' in m.label and m.value=='2' for m in at.metric)
    at.number_input(key='vq_ev').set_value(5.0).run()
    assert not at.exception and calls==['FIX','TEST']
    assert any('Candidată' in m.label and m.value=='0' for m in at.metric)


def test_english_labels_and_missing_data(monkeypatch):
    monkeypatch.setattr(ui,'fetch_metrics',lambda symbol:{'symbol':symbol,'kind':None,'name':symbol})
    at=AppTest.from_function(page)
    at.session_state['lang']='EN'
    at.run()
    assert not at.exception and any(b.label=='Run Value + Quality' for b in at.button)
    at.checkbox(key='vq_portfolio').uncheck();at.checkbox(key='vq_watchlist').uncheck()
    at.text_area(key='vq_manual').set_value('MISSING')
    at.button(key='vq_run').click().run()
    assert not at.exception
    assert any('Insufficient data' in m.label and m.value=='1' for m in at.metric)


def test_strategies_exposes_screener_with_empty_portfolio(monkeypatch):
    def strategies_page():
        import pandas as pd
        from strategies_ui import render_strategies_tab
        render_strategies_tab(pd.DataFrame(columns=['ticker','name']))
    at=AppTest.from_function(strategies_page).run()
    assert not at.exception and any(b.key=='vq_run' for b in at.button)
