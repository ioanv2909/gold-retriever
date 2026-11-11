"""Value + Quality screener, using public fundamentals and session-local selections."""
from urllib.parse import quote

import pandas as pd
import streamlit as st

from i18n import lang
from userctx import current_user
from yf_compat import yf, YFINANCE_AVAILABLE
import value_quality as vq


def tr(ro, en):
    return en if lang() == 'EN' else ro


@st.cache_data(ttl=21600, show_spinner=False)
def fetch_metrics(symbol):
    if not YFINANCE_AVAILABLE:
        return {'symbol': symbol, 'name': symbol, 'kind': None, 'error': 'provider_unavailable'}
    try:
        return vq.extract_metrics(yf.Ticker(symbol), symbol)
    except Exception:
        return {'symbol': symbol, 'name': symbol, 'kind': None, 'error': 'provider_error'}


def status_label(key):
    return {'candidate': tr('🟢 Candidată pentru analiză', '🟢 Research candidate'),
            'review': tr('🟡 De verificat', '🟡 Needs review'),
            'insufficient': tr('⚪ Date insuficiente', '⚪ Insufficient data'),
            'rejected': tr('🔴 Nu trece filtrele', '🔴 Fails filters'),
            'excluded': tr('— Exclusă', '— Excluded')}[key]


def _details(metrics, outcome, rules):
    names = {'stock': tr('Companie listată', 'Listed company'), 'sector': tr('Sector permis', 'Allowed sector'),
             'country': tr('Țara sediului permisă', 'Allowed domicile'), 'positive_ebit': 'EBIT TTM > 0',
             'ev_ebit': 'EV/EBIT TTM', 'roa': 'ROA %', 'growth': tr('Creșterea veniturilor %', 'Revenue growth %'),
             'history': tr('EBIT TTM / mediana istorică', 'EBIT TTM / historical median'),
             'ev_sign': tr('Enterprise Value', 'Enterprise value')}
    reasons = {'not_stock': tr('Preset pentru acțiuni, nu ETF-uri sau alte instrumente.', 'This preset is for stocks, not ETFs or other instruments.'),
               'currency_mismatch': tr('EV și EBIT nu au monede confirmate compatibile.', 'EV and EBIT do not have confirmed compatible currencies.'),
               'history_missing': tr('Sunt necesari 3 ani anteriori de EBIT comparabili.', 'Three comparable prior annual EBIT values are required.'),
               'ttm_missing': tr('EBIT TTM lipsește sau este prea vechi.', 'TTM EBIT is missing or stale.'),
               'unusual_ebit': tr('Profit neobișnuit sau ani cu pierderi; verificare manuală.', 'Unusual profit or historical losses; manual review needed.'),
               'nonpositive_ev': tr('EV ≤ 0: verifică datele și poziția de numerar.', 'EV ≤ 0: check the data and cash position.')}
    states = {'pass': tr('Trece', 'Pass'), 'fail': tr('Nu trece', 'Fail'), 'missing': tr('Lipsește', 'Missing'), 'review': tr('De verificat', 'Review')}
    rows = [{tr('Criteriu', 'Criterion'): names[c['key']], tr('Valoare', 'Value'): c.get('value'),
             tr('Prag', 'Threshold'): c.get('limit'), tr('Stare', 'Status'): states[c['state']],
             tr('Explicație', 'Explanation'): reasons.get(c.get('reason'), tr('Date indisponibile.', 'Data unavailable.') if c['state'] == 'missing' else '')}
            for c in outcome['checks']]
    st.dataframe(pd.DataFrame(rows).astype({tr('Valoare', 'Value'): str, tr('Prag', 'Threshold'): str}).replace({'None': '—'}),
                 hide_index=True, width='stretch')
    st.caption(tr('EV/EBIT ≤ prag; EBIT > 0; ROA și creșterea veniturilor ≥ prag. Sectoarele și țările sunt filtre de eligibilitate.',
                  'EV/EBIT ≤ threshold; EBIT > 0; ROA and revenue growth ≥ threshold. Sectors and countries are eligibility filters.'))
    period = metrics.get('ebit_period') or '—'
    basis = {'reported_ttm': tr('TTM raportat', 'Reported TTM'), 'four_quarters': tr('Suma a 4 trimestre consecutive', 'Sum of 4 consecutive quarters')}.get(metrics.get('ebit_basis'), tr('Indisponibil', 'Unavailable'))
    st.caption(tr('EBIT: {basis}; perioada încheiată la {period}. Monedă EV: {ev}; monedă situații financiare: {fin}.',
                  'EBIT: {basis}; period ended {period}. EV currency: {ev}; financial statement currency: {fin}.').format(
                      basis=basis, period=period, ev=metrics.get('currency') or '—', fin=metrics.get('financial_currency') or '—'))
    history = metrics.get('ebit_history') or []
    if history:
        st.markdown('**' + tr('Istoric EBIT anual', 'Annual EBIT history') + '**')
        hist = pd.DataFrame(history).rename(columns={'period': tr('Sfârșit perioadă', 'Period end'), 'ebit': 'EBIT'})
        st.dataframe(hist, hide_index=True, width='stretch', column_config={'EBIT': st.column_config.NumberColumn(format='localized')})
        st.caption(tr('Comparația folosește 3 ani anteriori perioadei TTM. Un salt peste prag declanșează verificare manuală, nu dovedește un câștig excepțional.',
                      'The comparison uses 3 years preceding the TTM period. A jump above the threshold requires review; it does not prove a one-off gain.'))
    st.caption(tr('Date publice Yahoo Finance, colectate la: ', 'Public Yahoo Finance data, retrieved at: ') + (metrics.get('fetched_at') or '—'))
    st.link_button(tr('Deschide sursa Yahoo Finance', 'Open Yahoo Finance source'), 'https://finance.yahoo.com/quote/' + quote(metrics['symbol'], safe='') + '/financials/')


def render_value_quality(vdf):
    with st.expander('Value + Quality', expanded=True):
        st.caption(tr('Filtru pentru cercetare: EV/EBIT TTM ≤ 15, ROA ≥ 10%, venituri în creștere și verificarea istoricului EBIT. Pragurile sunt configurabile.',
                      'Research screen: EV/EBIT TTM ≤ 15, ROA ≥ 10%, growing revenue and an EBIT history check. Thresholds are configurable.'))
        st.caption(tr('Nu este un screener global. Țara reprezintă sediul companiei; disponibilitatea instrumentului se verifică la broker. Datele lipsă nu sunt considerate criterii trecute.',
                      'This is not a global screener. Country means company domicile; check tradability with your broker. Missing data never counts as a passed criterion.'))
        left, right = st.columns(2)
        use_portfolio = left.checkbox(tr('Include portofoliul selectat', 'Include selected portfolio'), value=True, key='vq_portfolio')
        use_watchlist = right.checkbox(tr('Include watchlist', 'Include watchlist'), value=True, key='vq_watchlist')
        manual = st.text_area(tr('Simboluri Yahoo suplimentare', 'Additional Yahoo symbols'), placeholder='AAPL, MSFT, AJIS.T', key='vq_manual')
        a,b,c = st.columns(3)
        max_ev = a.number_input('EV/EBIT TTM ≤', min_value=0.1, max_value=100.0, value=15.0, step=0.5, key='vq_ev')
        min_roa = b.number_input('ROA % ≥', min_value=0.0, max_value=100.0, value=10.0, step=0.5, key='vq_roa')
        min_growth = c.number_input(tr('Creștere venituri % ≥', 'Revenue growth % ≥'), min_value=-100.0, max_value=1000.0, value=0.0, step=1.0, key='vq_growth')
        growth_labels = {'yoy': tr('YoY raportat de Yahoo', 'YoY reported by Yahoo'), 'cagr_3y': tr('CAGR venituri · 3 ani', 'Revenue CAGR · 3 years')}
        basis = st.selectbox(tr('Perioada creșterii', 'Growth period'), list(growth_labels), format_func=growth_labels.get, key='vq_growth_period')
        st.caption(tr('YoY este indicatorul revenueGrowth furnizat de Yahoo; CAGR este calculat din venituri anuale pe 3 ani. Nu se înlocuiesc automat unul cu altul.',
                      'YoY is Yahoo’s revenueGrowth field; CAGR is calculated from annual revenues over 3 years. Neither is silently substituted for the other.'))
        sectors = ['Financial Services','Technology','Healthcare','Industrials','Consumer Cyclical','Consumer Defensive','Energy','Basic Materials','Real Estate','Utilities','Communication Services']
        excluded = st.multiselect(tr('Sectoare excluse', 'Excluded sectors'), sectors, default=['Financial Services'], key='vq_excluded')
        countries = st.text_input(tr('Țările sediilor permise · opțional, separate prin virgulă', 'Allowed company domiciles · optional, comma separated'),
                                  placeholder='United States, Japan, Sweden', key='vq_countries')
        history = st.checkbox(tr('Cere verificarea istoricului EBIT', 'Require EBIT history check'), value=True, key='vq_history')
        spike = st.number_input(tr('EBIT TTM / mediana a 3 ani anteriori · maxim', 'TTM EBIT / median of 3 prior years · maximum'),
                                min_value=1.0,max_value=10.0,value=2.0,step=0.25,key='vq_spike',disabled=not history)
        refresh = st.checkbox(tr('Reîncarcă datele din Yahoo', 'Reload data from Yahoo'), value=False, key='vq_reload')
        rules = vq.Rules(max_ev,min_roa,min_growth,basis,tuple(excluded),tuple(c.strip() for c in countries.split(',') if c.strip()),history,spike)
        result_key = 'vq_results_' + str(current_user() or '_legacy')
        if st.button(tr('Analizează Value + Quality', 'Run Value + Quality'), key='vq_run', type='primary'):
            from yahoo import resolve_yahoo_symbol
            from watchlist import load_watchlist
            portfolio = vdf.to_dict('records') if use_portfolio and vdf is not None and not vdf.empty else []
            try:
                universe = vq.build_universe(portfolio, load_watchlist() if use_watchlist else [], manual, resolve_yahoo_symbol)
            except ValueError as exc:
                st.error(str(exc));universe = []
            if not universe:
                st.info(tr('Selectează o sursă sau introdu simboluri Yahoo valide; maximum 50 per analiză.', 'Select a source or enter valid Yahoo symbols; at most 50 per analysis.'))
            else:
                results = []
                progress = st.progress(0.0)
                for i, item in enumerate(universe):
                    if refresh:
                        fetch_metrics.clear(item['symbol'])
                    metrics = fetch_metrics(item['symbol'])
                    results.append({'metrics': metrics, 'origins': item['origins']})
                    progress.progress((i+1)/len(universe))
                progress.empty()
                st.session_state[result_key] = results
        results = st.session_state.get(result_key) or []
        if not results:
            st.caption(tr('Datele sunt încărcate doar la apăsarea butonului. Cache public: 6 ore.', 'Data loads only when you press Run. Public data cache: 6 hours.'))
            return
        evaluated = [(r['metrics'], vq.evaluate(r['metrics'], rules), r['origins']) for r in results]
        evaluated.sort(key=lambda r: (vq.number(r[0].get('ev_ebit')) is None, vq.number(r[0].get('ev_ebit')) or 0, r[0]['symbol']))
        st.caption(tr('Pragurile se aplică imediat. Schimbarea listei de simboluri necesită o nouă analiză.',
                      'Threshold changes apply immediately. Changes to the symbol list require another run.'))
        for col, status in zip(st.columns(3), ['candidate','review','insufficient']):
            col.metric(status_label(status), sum(o['status']==status for _,o,_ in evaluated))
        filter_labels = {'all':tr('Toate','All'), **{k:status_label(k) for k in ('candidate','review','insufficient','rejected','excluded')}}
        flt = st.selectbox(tr('Rezultate afișate', 'Displayed results'), list(filter_labels), format_func=filter_labels.get, key='vq_filter')
        shown = [r for r in evaluated if flt=='all' or r[1]['status']==flt]
        rows = [{'Symbol':m['symbol'],tr('Companie','Company'):m.get('name') or m['symbol'],tr('Stare','Status'):status_label(o['status']),
                 'EV/EBIT TTM':m.get('ev_ebit'),'ROA %':m.get('roa_pct'),tr('Creștere venituri %','Revenue growth %'):m.get('revenue_yoy_pct' if basis=='yoy' else 'revenue_cagr_3y_pct'),
                 tr('Sursă listă','List source'):', '.join(origins)} for m,o,origins in shown]
        if rows:
            st.dataframe(pd.DataFrame(rows),hide_index=True,width='stretch',column_config={
                key:st.column_config.NumberColumn(format='%.2f') for key in ['EV/EBIT TTM','ROA %',tr('Creștere venituri %','Revenue growth %')]})
            selected = st.selectbox(tr('Detalii companie', 'Company details'),[m['symbol'] for m,_,_ in shown],key='vq_detail')
            m,outcome,_ = next(r for r in shown if r[0]['symbol']==selected)
            _details(m,outcome,rules)
        else:
            st.info(tr('Nicio companie în categoria selectată.', 'No companies in this category.'))
        st.caption(tr('Candidate pentru analiză, nu recomandări de cumpărare. Nu se calculează ordine de tranzacționare.',
                      'Research candidates, not buy recommendations. No trade orders are generated.'))
