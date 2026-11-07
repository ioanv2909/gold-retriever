"""Fereastra initiala a graficelor care se pot trage in timp (fara UI): se incarca o perioada mai lunga,
iar graficul se deschide pe perioada aleasa; la tragere apar si datele dinainte."""
import pandas as pd

# perioada aleasa (CHART_PERIODS) -> perioada incarcata de la Yahoo, cu acelasi interval (~3 ferestre)
CHART_LOAD = {"1Z": "5d", "1S": "1mo", "1L": "3mo", "3L": "1y", "6L": "2y", "YTD": "2y", "1A": "2y",
              "3A": "10y", "5A": "max", "Max": "max"}
EXTRA_WINDOWS = 2  # graficul valorii: cate ferestre de dinainte se mai incarca


def view_start(index, yf_period):
    """Inceputul ferestrei alese (perioada yfinance: 1d, 5d, Nmo, Ny, ytd, max) in datele incarcate; None = tot."""
    if index is None or len(index) == 0 or yf_period == "max":
        return None
    idx = pd.DatetimeIndex(index)
    last = idx.max()
    if yf_period == "ytd":
        return pd.Timestamp(year=last.year, month=1, day=1, tz=last.tz)
    if yf_period.endswith("d"):  # zile de tranzactionare, ca la yfinance
        days = sorted(set(idx.normalize()))
        n = int(yf_period[:-1])
        first_day = days[-n] if len(days) >= n else days[0]
        return idx[idx.normalize() >= first_day].min()
    if yf_period.endswith("mo"):
        return last - pd.DateOffset(months=int(yf_period[:-2]))
    if yf_period.endswith("y"):
        return last - pd.DateOffset(years=int(yf_period[:-1]))
    return None  # perioada necunoscuta: tot graficul


def padded_range(values, pad=0.05):
    """[min, max] cu o margine, pentru axa Y fixa; None fara valori."""
    vals = [float(v) for v in values if v is not None and pd.notna(v)]
    if not vals:
        return None
    lo, hi = min(vals), max(vals)
    p = max((hi - lo) * pad, abs(hi) * 0.0005)
    return [lo - p, hi + p]


# Axa Y urmeaza ce se vede: dupa fiecare desenare a unui grafic tras in timp (dragmode "pan"), intervalul Y
# devine min/max-ul punctelor din fereastra X, cu o margine. Plotly nu e expus global in Streamlit, deci
# schimbarea se trimite prin handler-ul butoanelor de zoom din bara graficului (seteaza orice atribut de layout).
# Daca ceva lipseste (alta versiune Plotly), graficul ramane cu axa fixa trimisa din Python.
Y_AUTO_JS = r"""
var w = window.parent || window;
if (!w.__grYAuto) {
  w.__grYAuto = true;
  var PAD = 0.08;
  var relayoutFn = function (gd) {
    var mb = gd._fullLayout && gd._fullLayout._modeBar;
    var groups = (mb && mb.buttons) || [];
    for (var i = 0; i < groups.length; i++) {
      for (var j = 0; j < groups[i].length; j++) {
        var b = groups[i][j];
        if (b && b.name === 'zoomIn2d' && typeof b.click === 'function') return b.click;
      }
    }
    return null;
  };
  var fit = function (gd) {
    try {
      var fl = gd._fullLayout, xa = fl && fl.xaxis, ya = fl && fl.yaxis;
      if (!xa || !ya || fl.dragmode !== 'pan' || !gd.calcdata) return;
      var x0 = xa.r2l(xa.range[0]), x1 = xa.r2l(xa.range[1]);
      var lo = Infinity, hi = -Infinity;
      gd.calcdata.forEach(function (cd) {
        var tr = cd && cd[0] && cd[0].trace;
        if (!tr || tr.visible !== true || (tr.yaxis || 'y') !== 'y') return;
        cd.forEach(function (p) {
          if (p && isFinite(p.x) && isFinite(p.y) && p.x >= x0 && p.x <= x1) {
            if (p.y < lo) lo = p.y;
            if (p.y > hi) hi = p.y;
          }
        });
      });
      if (!isFinite(lo) || !isFinite(hi)) return;
      var pad = Math.max((hi - lo) * PAD, Math.abs(hi) * 0.0005);
      var r = [lo - pad, hi + pad], cur = [ya.r2l(ya.range[0]), ya.r2l(ya.range[1])];
      var tol = Math.max(Math.abs(r[1] - r[0]) * 1e-6, 1e-9);
      if (Math.abs(cur[0] - r[0]) < tol && Math.abs(cur[1] - r[1]) < tol) return;
      var click = relayoutFn(gd);
      if (!click) return;
      var el = {getAttribute: function (k) { return k === 'data-attr' ? 'yaxis.range' : (k === 'data-val' ? r : null); },
                setAttribute: function () {}};
      click(gd, {currentTarget: el});
    } catch (e) { /* graficul ramane cu axa fixa */ }
  };
  var scan = function () {
    w.document.querySelectorAll('.js-plotly-plot').forEach(function (gd) {
      if (gd.__grYAuto || typeof gd.on !== 'function') return;
      gd.__grYAuto = true;
      gd.on('plotly_afterplot', function () { fit(gd); });
      fit(gd);
    });
  };
  w.setInterval(scan, 700);
  scan();
}
"""

