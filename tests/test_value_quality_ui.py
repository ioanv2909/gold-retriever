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
    assert at.checkbox(key='vq_portfolio').value is False
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
    assert at.checkbox(key='vq_portfolio').value is False
    at.checkbox(key='vq_watchlist').uncheck()
    at.text_area(key='vq_manual').set_value('MISSING')
    at.button(key='vq_run').click().run()
    assert not at.exception
    assert any('Insufficient data' in m.label and m.value=='1' for m in at.metric)


def test_strategies_no_longer_contains_watchlist_screener(monkeypatch):
    def strategies_page():
        import pandas as pd
        from strategies_ui import render_strategies_tab
        render_strategies_tab(pd.DataFrame(columns=['ticker','name']))
    at=AppTest.from_function(strategies_page).run()
    assert not at.exception and not any(b.key=='vq_run' for b in at.button)


def watchlist_page():
    import pandas as pd
    from watchlist_ui import render_watchlist_tab
    render_watchlist_tab(pd.DataFrame([{'ticker':'HELD','name':'Held fixture'}]))


def _watchlist_fixtures(monkeypatch):
    import watchlist
    import watchlist_ui
    import yahoo
    monkeypatch.setattr(watchlist,'load_watchlist',lambda:[{'symbol':'FIX'}])
    monkeypatch.setattr(watchlist_ui,'load_watchlist',lambda:[{'symbol':'FIX'}])
    monkeypatch.setattr(watchlist_ui,'load_watchlist_cache',lambda:{'FIX':{'name':'Watch fixture'}})
    monkeypatch.setattr(yahoo,'resolve_yahoo_symbol',lambda s:s)
    calls=[]
    def fetch(symbol):
        calls.append(symbol)
        return vq.extract_metrics(ticker(),symbol,date(2026,11,11))
    monkeypatch.setattr(ui,'fetch_metrics',fetch)
    return calls


def test_watchlist_is_default_portfolio_is_optional_and_result_appears_in_list(monkeypatch):
    calls=_watchlist_fixtures(monkeypatch)
    at=AppTest.from_function(watchlist_page).run()
    assert not at.exception and calls==[]
    assert not any(b.key=='vq_run' for b in at.button)
    at.button_group[0].set_value('value_quality').run()
    assert not at.exception
    assert at.checkbox(key='vq_watchlist').value is True
    assert at.checkbox(key='vq_portfolio').value is False
    at.button(key='vq_run').click().run()
    assert not at.exception and calls==['FIX']
    at.button_group[0].set_value('list').run()
    assert not at.exception and calls==['FIX']
    html=next(m.value for m in at.markdown if 'grtbl' in m.value)
    assert 'title="FIX"' in html and 'Watch fixture' in html and '>FIX<' not in html
    assert 'Candidată' in html
    at.button_group[0].set_value('value_quality').run()
    at.number_input(key='vq_ev').set_value(5.0).run()
    at.button_group[0].set_value('list').run()
    assert 'Nu trece' in next(m.value for m in at.markdown if 'grtbl' in m.value)
    assert calls==['FIX']
    at.button_group[0].set_value('value_quality').run()
    assert at.number_input(key='vq_ev').value == 5.0
    assert at.checkbox(key='vq_watchlist').value is True
    at.checkbox(key='vq_portfolio').check().run()
    at.button(key='vq_run').click().run()
    assert not at.exception and calls==['FIX','HELD','FIX']


def test_previous_mixed_screen_does_not_override_watchlist_defaults(monkeypatch):
    calls=_watchlist_fixtures(monkeypatch)
    at=AppTest.from_function(watchlist_page)
    at.session_state['vq_portfolio']=True
    at.session_state['vq_watchlist']=False
    at.session_state['vq_results__legacy']=[{'metrics':{'symbol':'HELD','kind':'EQUITY'},'origins':['portfolio']}]
    at.run()
    at.button_group[0].set_value('value_quality').run()
    assert not at.exception
    assert at.checkbox(key='vq_portfolio').value is False
    assert at.checkbox(key='vq_watchlist').value is True
    assert not at.metric and calls==[]


def test_watchlist_empty_and_english_navigation(monkeypatch):
    import watchlist
    import watchlist_ui
    monkeypatch.setattr(watchlist,'load_watchlist',lambda:[])
    monkeypatch.setattr(watchlist_ui,'load_watchlist',lambda:[])
    monkeypatch.setattr(watchlist_ui,'load_watchlist_cache',lambda:{})
    at=AppTest.from_function(watchlist_page)
    at.session_state['lang']='EN'
    at.run()
    assert not at.exception and at.button_group[0].options==['List','Value + Quality']
    at.button_group[0].set_value('value_quality').run()
    assert not at.exception and at.checkbox(key='vq_watchlist').value is True
    at.button(key='vq_run').click().run()
    assert not at.exception and any('Select a source' in e.value for e in at.info)
