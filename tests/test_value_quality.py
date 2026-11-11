from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest

import value_quality as vq

TODAY=date(2026,11,11)
Q=pd.to_datetime(['2026-09-30','2026-06-30','2026-03-31','2025-12-31'])
Y=pd.to_datetime(['2025-12-31','2024-12-31','2023-12-31','2022-12-31'])


def ticker(**info):
    base={'quoteType':'EQUITY','currency':'USD','financialCurrency':'USD','enterpriseValue':1200,
          'returnOnAssets':.12,'revenueGrowth':.03,'sector':'Technology','country':'United States','longName':'Fixture'}
    base.update(info)
    return SimpleNamespace(info=base,ttm_income_stmt=pd.DataFrame({'2026-09-30':[100]},index=['EBIT']),
        quarterly_income_stmt=pd.DataFrame([[25,25,25,25]],index=['EBIT'],columns=Q),
        income_stmt=pd.DataFrame([[90,80,70,60],[1331,1210,1100,1000]],index=['EBIT','Total Revenue'],columns=Y))


def metrics(**extra):
    m=vq.extract_metrics(ticker(), 'FIX', TODAY);m.update(extra);return m


def test_exact_default_rules_and_units():
    m=metrics();r=vq.evaluate(m)
    assert m['ebit_ttm']==100 and m['ev_ebit']==12
    assert m['roa_pct']==12 and m['revenue_yoy_pct']==3
    assert m['revenue_cagr_3y_pct']==pytest.approx(10,abs=.02)
    assert r['status']=='candidate' and r['ebit_ratio']==1.25
    assert all(c['state']=='pass' for c in r['checks'])


def test_quarter_fallback_requires_four_complete_consecutive_quarters():
    t=ticker();t.ttm_income_stmt=None
    m=vq.extract_metrics(t,'FIX',TODAY)
    assert m['ebit_ttm']==100 and m['ebit_basis']=='four_quarters'
    t.quarterly_income_stmt.iloc[0,1]=float('nan')
    t.quarterly_income_stmt[pd.Timestamp('2025-09-30')]=25
    assert vq.extract_metrics(t,'FIX',TODAY)['ebit_ttm'] is None
    t.quarterly_income_stmt=pd.DataFrame([[25]*4],index=['EBIT'],columns=pd.to_datetime(['2026-09-30','2026-03-31','2025-12-31','2025-09-30']))
    assert vq.extract_metrics(t,'FIX',TODAY)['ebit_ttm'] is None


def test_never_substitutes_annual_ebit_or_ebitda():
    t=ticker();t.ttm_income_stmt=pd.DataFrame({'2026-09-30':[900]},index=['EBITDA']);t.quarterly_income_stmt=None
    m=vq.extract_metrics(t,'FIX',TODAY)
    assert m['ebit_ttm'] is None and m['ev_ebit'] is None
    assert vq.evaluate(m)['status']=='insufficient'


@pytest.mark.parametrize('currency,financial,matched',[('USD','CNY',False),('USD',None,False),('GBp','GBP',True),('USD','USD',True)])
def test_currency_compatibility_and_ev_major_units(currency,financial,matched):
    m=vq.extract_metrics(ticker(currency=currency,financialCurrency=financial),'FIX',TODAY)
    assert m['currency_match'] is matched
    assert m['ev_ebit']==(12 if matched else None)
    assert vq.evaluate(m)['status']==('candidate' if matched else 'insufficient')


@pytest.mark.parametrize('value',[0,-10])
def test_nonpositive_ebit_is_rejected_not_a_cheap_multiple(value):
    t=ticker();t.ttm_income_stmt.iloc[0,0]=value
    m=vq.extract_metrics(t,'FIX',TODAY)
    assert m['ev_ebit'] is None
    assert vq.evaluate(m)['status']=='rejected'


def test_missing_roa_growth_and_sector_do_not_pass():
    for kwargs in [{'roa_pct':None},{'revenue_yoy_pct':None},{'sector':None}]:
        assert vq.evaluate(metrics(**kwargs))['status']=='insufficient'
    assert vq.evaluate(metrics(roa_pct=float('nan')))['status']=='insufficient'
    assert vq.evaluate(metrics(revenue_yoy_pct=-.1))['status']=='rejected'


def test_reliability_spike_losses_and_short_history():
    assert vq.evaluate(metrics(ebit_ttm=400))['status']=='review'
    m=metrics();m['ebit_history'][1]['ebit']=-10
    assert vq.evaluate(m)['status']=='review'
    m=metrics();m['ebit_history']=m['ebit_history'][:2]
    assert vq.evaluate(m)['status']=='insufficient'
    assert vq.evaluate(m,vq.Rules(require_history=False))['status']=='candidate'


def test_history_must_precede_ttm_and_be_recent_consecutive_years():
    m=metrics(ebit_period='2025-12-31')
    result=vq.evaluate(m)
    assert result['status']=='candidate'
    assert result['ebit_ratio']==pytest.approx(100/70)
    m['ebit_history']=[{'period':'2015-12-31','ebit':100},{'period':'2014-12-31','ebit':100},{'period':'2013-12-31','ebit':100}]
    assert vq.evaluate(m)['status']=='insufficient'


def test_stale_or_future_ttm_is_not_current_data():
    t=ticker();t.quarterly_income_stmt=None
    for stamp in ['2024-12-31','2027-03-31']:
        t.ttm_income_stmt=pd.DataFrame({stamp:[100]},index=['EBIT'])
        assert vq.extract_metrics(t,'FIX',TODAY)['ebit_ttm'] is None


def test_configurable_filters_exclusions_and_growth_period():
    assert vq.evaluate(metrics(sector='Financial Services'))['status']=='excluded'
    assert vq.evaluate(metrics(kind='ETF'))['status']=='excluded'
    assert vq.evaluate(metrics(),vq.Rules(countries=('Japan',)))['status']=='excluded'
    assert vq.evaluate(metrics(),vq.Rules(max_ev_ebit=10))['status']=='rejected'
    assert vq.evaluate(metrics(revenue_yoy_pct=-5),vq.Rules(growth_period='cagr_3y'))['status']=='candidate'
    assert vq.evaluate(metrics(revenue_yoy_pct=-5))['status']=='rejected'
    assert vq.evaluate(metrics(enterprise_value=-10,ev_ebit=-.1))['status']=='review'


@pytest.mark.parametrize('kwargs',[{'max_ev_ebit':0},{'min_roa_pct':float('nan')},{'max_ebit_spike':.5},{'growth_period':'unknown'}])
def test_invalid_rules_rejected(kwargs):
    with pytest.raises(ValueError):vq.Rules(**kwargs)


def test_universe_maps_broker_tickers_and_deduplicates_origins():
    rows=vq.build_universe([{'ticker':'FIX_US_EQ','name':'Fixture'}],[{'symbol':'FIX'}],'fix, MSFT; FIX',lambda s:s.replace('_US_EQ',''))
    assert [r['symbol'] for r in rows]==['FIX','MSFT']
    assert rows[0]['origins']==['portfolio','watchlist','manual']
    with pytest.raises(ValueError):vq.build_universe(manual='AAPL https://invalid.example')
    with pytest.raises(ValueError):vq.build_universe(manual=','.join('FIX'+str(i) for i in range(51)))


def test_provider_properties_missing_is_insufficient():
    m=vq.extract_metrics(SimpleNamespace(info=None),'FIX',TODAY)
    assert vq.evaluate(m)['status']=='insufficient'
