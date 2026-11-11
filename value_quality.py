"""Value + Quality screening of a finite symbol list; no trading or buy signals."""
from dataclasses import dataclass
from datetime import date, datetime, timezone
import math
import re
import statistics

import pandas as pd

MAX_SYMBOLS = 50
MAX_REPORT_AGE_DAYS = 190


def number(value):
    if isinstance(value, (bool, str)):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _safe(fn):
    try:
        return fn()
    except Exception:
        return None


def _series(frame, row):
    if not isinstance(frame, pd.DataFrame) or row not in frame.index:
        return []
    values = frame.loc[row]
    if not isinstance(values, pd.Series):
        return []
    result = {}
    for label, value in values.items():
        try:
            stamp = pd.Timestamp(label).date()
        except (TypeError, ValueError, OverflowError):
            continue
        if stamp is pd.NaT or not isinstance(stamp, date):
            continue
        # Preserve missing newest periods; never fill a missing quarter with an older one.
        result.setdefault(stamp, number(value))
    return sorted(result.items(), reverse=True)


def _fresh(stamp, today):
    return 0 <= (today - stamp).days <= MAX_REPORT_AGE_DAYS


def _ttm_ebit(trailing, quarterly, today):
    direct = _series(trailing, 'EBIT')
    if direct and direct[0][1] is not None and _fresh(direct[0][0], today):
        return direct[0][1], direct[0][0], 'reported_ttm'
    quarters = _series(quarterly, 'EBIT')[:4]
    if len(quarters) != 4 or not _fresh(quarters[0][0], today) or any(v is None for _, v in quarters):
        return None, None, None
    if not all(60 <= (quarters[i][0] - quarters[i + 1][0]).days <= 120 for i in range(3)):
        return None, None, None
    if not 235 <= (quarters[0][0] - quarters[-1][0]).days <= 315:
        return None, None, None
    return sum(v for _, v in quarters), quarters[0][0], 'four_quarters'


def _currency(code):
    if code == 'GBp':
        return 'GBP'  # EV/market cap are major-currency amounts, unlike the quoted share price.
    if code == 'ZAc':
        return 'ZAR'
    return str(code).upper() if code else None


def extract_metrics(ticker, symbol, today=None):
    """Use EBIT specifically, not EBITDA or an annual profit mislabeled as TTM."""
    today = today or date.today()
    info = _safe(lambda: ticker.info) or {}
    if not isinstance(info, dict):
        info = {}
    result = {'symbol': symbol, 'name': info.get('longName') or info.get('shortName') or symbol,
              'kind': info.get('quoteType'), 'sector': info.get('sector'), 'country': info.get('country'),
              'currency': _currency(info.get('currency')), 'financial_currency': _currency(info.get('financialCurrency')),
              'fetched_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
              'enterprise_value': number(info.get('enterpriseValue')), 'ebit_ttm': None, 'ev_ebit': None,
              'roa_pct': None, 'revenue_yoy_pct': None, 'revenue_cagr_3y_pct': None,
              'ebit_history': [], 'ebit_period': None, 'ebit_basis': None, 'currency_match': False}
    if result['kind'] != 'EQUITY':
        return result
    trailing = _safe(lambda: ticker.ttm_income_stmt)
    quarterly = _safe(lambda: ticker.quarterly_income_stmt)
    annual = _safe(lambda: ticker.income_stmt)
    ebit, period, basis = _ttm_ebit(trailing, quarterly, today)
    result.update(ebit_ttm=ebit, ebit_period=period.isoformat() if period else None, ebit_basis=basis)
    matched = bool(result['currency'] and result['currency'] == result['financial_currency'])
    result['currency_match'] = matched
    if matched and ebit is not None and ebit > 0 and result['enterprise_value'] is not None:
        result['ev_ebit'] = number(result['enterprise_value'] / ebit)
    roa = number(info.get('returnOnAssets'))
    result['roa_pct'] = roa * 100 if roa is not None else None
    growth = number(info.get('revenueGrowth'))
    result['revenue_yoy_pct'] = growth * 100 if growth is not None else None
    annual_revenue = _series(annual, 'Total Revenue')
    if len(annual_revenue) >= 4:
        end, newest = annual_revenue[0]; start, oldest = annual_revenue[3]
        days = (end - start).days
        if 0 <= (today - end).days <= 550 and 1000 <= days <= 1200 and newest is not None and oldest is not None and min(newest, oldest) > 0:
            result['revenue_cagr_3y_pct'] = ((newest / oldest) ** (365.25 / days) - 1) * 100
    result['ebit_history'] = [{'period': stamp.isoformat(), 'ebit': value}
                              for stamp, value in _series(annual, 'EBIT')[:6] if stamp <= today]
    return result


@dataclass(frozen=True)
class Rules:
    max_ev_ebit: float = 15.0
    min_roa_pct: float = 10.0
    min_growth_pct: float = 0.0
    growth_period: str = 'yoy'
    excluded_sectors: tuple = ('Financial Services',)
    countries: tuple = ()
    require_history: bool = True
    max_ebit_spike: float = 2.0

    def __post_init__(self):
        if (number(self.max_ev_ebit) is None or self.max_ev_ebit <= 0 or
                number(self.min_roa_pct) is None or number(self.min_growth_pct) is None or
                number(self.max_ebit_spike) is None or self.max_ebit_spike < 1 or
                self.growth_period not in ('yoy', 'cagr_3y')):
            raise ValueError('Invalid screening thresholds')


def evaluate(metrics, rules=None):
    rules = rules or Rules()
    m = metrics or {}
    checks = []
    def check(key, value, passed, limit=None, reason=None):
        state = 'missing' if value is None else ('pass' if passed else 'fail')
        checks.append({'key': key, 'value': value, 'limit': limit, 'state': state, 'reason': reason})
    kind = m.get('kind')
    if kind and kind != 'EQUITY':
        return {'status': 'excluded', 'checks': [{'key': 'stock', 'state': 'fail', 'value': kind, 'reason': 'not_stock'}], 'ebit_ratio': None}
    check('stock', kind, kind == 'EQUITY')
    normalize = lambda v: str(v).strip().casefold().replace('financials', 'financial services')
    if rules.excluded_sectors:
        sector = m.get('sector')
        check('sector', sector, normalize(sector) not in {normalize(s) for s in rules.excluded_sectors})
    if rules.countries:
        country = m.get('country')
        check('country', country, normalize(country) in {normalize(c) for c in rules.countries})
    ebit = number(m.get('ebit_ttm'))
    check('positive_ebit', ebit, ebit is not None and ebit > 0, 0)
    ev = number(m.get('ev_ebit'))
    check('ev_ebit', ev, ev is not None and ev <= rules.max_ev_ebit, rules.max_ev_ebit,
          'currency_mismatch' if m.get('currency_match') is False else None)
    roa = number(m.get('roa_pct'))
    check('roa', roa, roa is not None and roa >= rules.min_roa_pct, rules.min_roa_pct)
    growth = number(m.get('revenue_yoy_pct' if rules.growth_period == 'yoy' else 'revenue_cagr_3y_pct'))
    check('growth', growth, growth is not None and growth >= rules.min_growth_pct, rules.min_growth_pct)
    ratio = None
    if rules.require_history:
        history = sorted([r for r in m.get('ebit_history', []) if r.get('period') and m.get('ebit_period') and r['period'] < m['ebit_period']], key=lambda r:r['period'], reverse=True)[:3]
        values = [number(r.get('ebit')) for r in history]
        try:
            dates = [date.fromisoformat(r['period']) for r in history]
            period = date.fromisoformat(m.get('ebit_period') or '')
            comparable = len(dates) == 3 and (period-dates[0]).days <= 550 and all(330 <= (dates[i]-dates[i+1]).days <= 400 for i in range(2))
        except (ValueError, TypeError):
            comparable = False
        if not comparable or len(values) < 3 or any(v is None for v in values):
            checks.append({'key': 'history', 'value': None, 'state': 'missing', 'reason': 'history_missing'})
        elif ebit is None:
            checks.append({'key': 'history', 'value': None, 'state': 'missing', 'reason': 'ttm_missing'})
        else:
            baseline = statistics.median(values)
            ratio = ebit / baseline if baseline > 0 else None
            unusual = any(v <= 0 for v in values) or ratio is None or ratio > rules.max_ebit_spike
            checks.append({'key': 'history', 'value': ratio, 'limit': rules.max_ebit_spike,
                           'state': 'review' if unusual else 'pass', 'reason': 'unusual_ebit' if unusual else None})
    if number(m.get('enterprise_value')) is not None and m['enterprise_value'] <= 0:
        checks.append({'key': 'ev_sign', 'value': m['enterprise_value'], 'state': 'review', 'reason': 'nonpositive_ev'})
    excluded = any(c['key'] in ('sector', 'country') and c['state'] == 'fail' for c in checks)
    states = {c['state'] for c in checks}
    status = ('excluded' if excluded else 'rejected' if 'fail' in states else
              'insufficient' if 'missing' in states else 'review' if 'review' in states else 'candidate')
    return {'status': status, 'checks': checks, 'ebit_ratio': ratio}


def build_universe(portfolio=(), watchlist=(), manual='', resolve=lambda s: s):
    result = {}
    def add(raw, origin, name=None, translate=True):
        resolved = resolve(raw) if translate else raw
        if not isinstance(resolved, str) or not resolved.strip():
            raise ValueError('Missing Yahoo symbol')
        symbol = resolved.strip().upper()
        if not re.fullmatch(r'[A-Z0-9][A-Z0-9.=-]{0,31}', symbol):
            raise ValueError('Invalid Yahoo symbol: ' + symbol[:40])
        row = result.setdefault(symbol, {'symbol': symbol, 'name': name or symbol, 'origins': []})
        if origin not in row['origins']:
            row['origins'].append(origin)
    for row in portfolio:
        if isinstance(row.get('ticker'), str) and row['ticker'].strip():
            add(row['ticker'], 'portfolio', row.get('name'))
    for row in watchlist:
        if isinstance(row, dict) and row.get('symbol'):
            add(row['symbol'], 'watchlist')
    for symbol in re.split(r'[\s,;]+', manual.strip()):
        if symbol:
            add(symbol, 'manual', translate=False)
    if len(result) > MAX_SYMBOLS:
        raise ValueError(f'At most {MAX_SYMBOLS} symbols per analysis')
    return list(result.values())
