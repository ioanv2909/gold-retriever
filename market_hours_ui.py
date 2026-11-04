"""Tab-ul Burse din pagina principala: intervalele de tranzactionare ale burselor cu pozitii, in ora locala."""
from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import market_hours as mh
import mobile
from i18n import t

OPEN = "#2e9e5b"
CLOSED = "#7a8ca5"


def _fmt_wait(now, when):
    if when is None:
        return "—"
    mins = int((when - now).total_seconds() // 60)
    d, rest = divmod(mins, 1440)
    h, m = divmod(rest, 60)
    span = (f"{d}d " if d else "") + (f"{h}h " if h or d else "") + f"{m}m"
    day = "" if when.date() == now.date() else t("mh.day." + str(when.weekday())) + " "
    return f"{day}{when:%H:%M} ({span})"


def _chart(items, day_start, now):
    day_end = day_start + timedelta(days=1)
    fig = go.Figure()
    labels = [lbl for lbl, *_ in items]
    for lbl, suffix, is_open, names in items:
        _, name, tz, sessions = mh.EXCHANGES[suffix]
        exch_hours = ", ".join(f"{a:%H:%M}–{b:%H:%M}" for a, b in sessions)
        for a, b in mh.sessions_between(suffix, day_start, day_end):
            fig.add_trace(go.Bar(
                y=[lbl], base=[a.replace(tzinfo=None)], x=[(b - a).total_seconds() * 1000], orientation="h",
                marker={"color": OPEN if is_open else CLOSED, "cornerradius": 4}, showlegend=False,
                text=f"{a:%H:%M}–{b:%H:%M}", textposition="inside", insidetextanchor="middle",
                hovertemplate=(f"<b>{name}</b><br>{t('mh.local')}: {a:%H:%M}–{b:%H:%M}<br>"
                               f"{t('mh.exch_time', tz=tz)}: {exch_hours}<br>"
                               + "<br>".join(names[:12]) + ("<br>…" if len(names) > 12 else "") + "<extra></extra>")))
    now_n = now.replace(tzinfo=None)
    fig.add_shape(type="line", x0=now_n, x1=now_n, y0=0, y1=1, yref="paper", line={"color": "#d64545", "width": 2})
    fig.add_annotation(x=now_n, y=1, yref="paper", text=f"{now:%H:%M}", showarrow=False, yanchor="bottom",
                       font={"color": "#d64545"})
    fig.update_layout(
        height=70 + 34 * len(items), margin={"l": 10, "r": 10, "t": 25, "b": 10}, bargap=0.35, barmode="overlay",
        xaxis={"type": "date", "range": [day_start.replace(tzinfo=None), day_end.replace(tzinfo=None)],
               "dtick": 2 * 3600 * 1000, "tickformat": "%H:%M", "showgrid": True},
        yaxis={"categoryorder": "array", "categoryarray": labels, "autorange": "reversed"})
    return fig


def render_market_hours_tab(vdf):
    """vdf: randurile pozitiilor din portofoliile selectate (ticker, name, yahoo_symbol)."""
    rows = vdf.to_dict("records") if vdf is not None and not vdf.empty else []
    groups, unknown = mh.group_positions(rows)
    if not groups:
        st.info(t("mh.empty"))
        return
    zone = mh.local_zone()
    now = datetime.now(zone)
    day_start = datetime.combine(now.date(), datetime.min.time(), zone)
    items, table = [], []
    for suffix, names in groups.items():
        key, name, _, _ = mh.EXCHANGES[suffix]
        is_open, change = mh.status(suffix, now)
        note = mh.day_note(suffix, mh._exchange_date(suffix, day_start))
        items.append((f"{'🟢' if is_open else '⚪'} {name} · {len(names)}", suffix, is_open, sorted(names)))
        table.append({t("mh.col.exchange"): name, t("mh.col.positions"): len(names),
                      t("mh.col.status"): (t("mh.open") if is_open else t("mh.closed"))
                      + (f" · {t('mh.note.' + note)}" if note else ""),
                      t("mh.col.next"): (t("mh.closes") if is_open else t("mh.opens")) + " " + _fmt_wait(now, change)})
    # ordinea: dupa ora de deschidere de azi (bursele fara sesiune azi la final)
    first = {s: (mh.sessions_between(s, day_start, day_start + timedelta(days=1)) or [(day_start + timedelta(days=2),)])[0][0]
             for _, s, _, _ in items}
    order = sorted(range(len(items)), key=lambda i: (first[items[i][1]], items[i][0]))
    items = [items[i] for i in order]
    table = [table[i] for i in order]

    st.caption(t("mh.caption", tz=str(zone), d=f"{now:%d.%m.%Y}"))
    render_market_strip(vdf)
    mobile.plotly_chart(_chart(items, day_start, now), width="stretch", key="mh_chart")
    st.dataframe(table, hide_index=True, width="stretch")
    if unknown:
        st.caption(t("mh.unknown", tickers=", ".join(sorted(str(x) for x in unknown))))


_STRIP_CSS = """<style>
.gr-mh{margin:.4rem 0 1rem 0;font-size:.85rem}
.gr-mh-row{display:flex;align-items:center;gap:.6rem;margin:.25rem 0}
.gr-mh-lbl{flex:0 0 28%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.gr-mh-lbl small{opacity:.65}
.gr-mh-track,.gr-mh-ticks{position:relative;flex:1 1 auto;height:1.35rem}
.gr-mh-track{background:rgba(128,128,128,.28);border-radius:5px;overflow:hidden}
.gr-mh-seg{position:absolute;top:0;bottom:0;background:#2e9e5b;opacity:.55;color:#fff;font-size:.72rem;
 display:flex;align-items:center;justify-content:center;white-space:nowrap;overflow:hidden}
.gr-mh-seg.on{opacity:1}
.gr-mh-now{position:absolute;top:-2px;bottom:-2px;width:2px;background:#d64545}
.gr-mh-ticks{height:.9rem;font-size:.68rem;opacity:.6}
.gr-mh-ticks span{position:absolute;transform:translateX(-50%)}
@media (max-width:640px){.gr-mh-row{flex-wrap:wrap;gap:.1rem}.gr-mh-lbl{flex-basis:100%}}
</style>"""


def _notes(bar):
    return "".join(f" · {t('mh.note.' + n)}" for n in sorted(bar.get("notes") or ()))


def _pct(dt, day_start):
    return max(0.0, min(100.0, (dt - day_start).total_seconds() / 864))


def render_market_strip(vdf):
    """Banda compacta din tabul Burse: o bara pe grup de burse cu acelasi
    program azi, gri = inchis, verde = deschis, linie rosie = acum."""
    import html
    rows = vdf.to_dict("records") if vdf is not None and not vdf.empty else []
    groups, _ = mh.group_positions(rows)
    if not groups:
        return
    zone = mh.local_zone()
    now = datetime.now(zone)
    day_start = datetime.combine(now.date(), datetime.min.time(), zone)
    now_pct = _pct(now, day_start)
    out = [_STRIP_CSS, '<div class="gr-mh">']
    for bar in mh.group_by_hours(groups, day_start, now):
        exch = ", ".join(bar["exchanges"])
        hours = ", ".join(f"{a:%H:%M}–{b:%H:%M}" for a, b in bar["sessions"]) or t("mh.closed_today")
        tip = html.escape(f"{exch} · {hours} · {t('mh.n_pos', n=bar['positions'])}{_notes(bar)}")
        segs = []
        for a, b in bar["sessions"]:
            left, width = _pct(a, day_start), _pct(b, day_start) - _pct(a, day_start)
            text = f"{a:%H:%M}–{b:%H:%M}" if width >= 14 else ""
            segs.append(f'<div class="gr-mh-seg{" on" if a <= now < b else ""}" '
                        f'style="left:{left:.2f}%;width:{width:.2f}%">{text}</div>')
        out.append(
            f'<div class="gr-mh-row" title="{tip}"><div class="gr-mh-lbl">{"🟢" if bar["open"] else "⚪"} '
            f'{html.escape(t("mh.region." + bar["region"]))} <small>{html.escape(exch)} · {bar["positions"]}{html.escape(_notes(bar))}</small></div>'
            f'<div class="gr-mh-track">{"".join(segs)}<div class="gr-mh-now" style="left:{now_pct:.2f}%"></div></div></div>')
    ticks = "".join(f'<span style="left:{h / 24 * 100:.2f}%">{h:02d}</span>' for h in range(0, 25, 3))
    out.append(f'<div class="gr-mh-row"><div class="gr-mh-lbl"></div><div class="gr-mh-ticks">{ticks}</div></div></div>')
    st.markdown("".join(out), unsafe_allow_html=True)


BAND_ROW_PX = 16
BAND_GAP_PX = 4
BAND_AXIS_PX = 26  # loc pentru etichetele axei X intre grafic si benzi
BAND_MAX_DAYS = 35


def add_market_bands(fig, vdf, x0, x1, height, margin_tb=70):
    """Benzi sub axa X a unui grafic in timp (x in ora locala, fara fus): pe fiecare rand un grup de burse cu
    acelasi program, gri = inchis, verde = deschis (aprins daca e deschis acum). Pe perioade mai lungi de
    BAND_MAX_DAYS doar starea curenta, ca text deasupra graficului. Intoarce inaltimea noua a figurii."""
    rows = vdf.to_dict("records") if vdf is not None and not vdf.empty else []
    groups, _ = mh.group_positions(rows)
    if not groups:
        return height
    zone = mh.local_zone()
    now = datetime.now(zone)
    bars = mh.group_by_hours(groups, mh.reference_day(now), now)
    x0, x1 = pd.Timestamp(x0).to_pydatetime(), pd.Timestamp(x1).to_pydatetime()
    if (x1 - x0).total_seconds() > BAND_MAX_DAYS * 86400:
        chips = "   ".join(f"{'🟢' if b['open'] else '⚪'} {t('mh.region.' + b['region'])}" for b in bars)
        fig.add_annotation(text=chips, xref="paper", yref="paper", x=1, y=1, xanchor="right", yanchor="bottom",
                           showarrow=False, font={"size": 11})
        return height
    n = len(bars)
    band_px = n * (BAND_ROW_PX + BAND_GAP_PX) + BAND_AXIS_PX
    new_height = height + band_px
    plot_px = new_height - margin_tb
    fig.update_yaxes(domain=[band_px / plot_px, 1])
    start, end = x0.replace(tzinfo=zone), x1.replace(tzinfo=zone)
    for i, bar in enumerate(bars):
        top = (n - i) * (BAND_ROW_PX + BAND_GAP_PX) / plot_px
        bottom = top - BAND_ROW_PX / plot_px
        common = {"xref": "x", "yref": "paper", "y0": bottom, "y1": top, "line": {"width": 0}, "layer": "below"}
        fig.add_shape(type="rect", x0=x0, x1=x1, fillcolor="rgba(128,128,128,0.28)", **common)
        for a, b in mh.sessions_between(bar["suffixes"][0], start, end):
            fig.add_shape(type="rect", x0=a.replace(tzinfo=None), x1=b.replace(tzinfo=None), fillcolor=OPEN,
                          opacity=1 if a <= now < b else 0.5, **common)
        fig.add_annotation(
            text=f"{'🟢' if bar['open'] else '⚪'} {t('mh.region.' + bar['region'])} · {', '.join(bar['exchanges'])}{_notes(bar)}",
            xref="paper", yref="paper", x=0.005, y=(top + bottom) / 2, xanchor="left", yanchor="middle",
            showarrow=False, font={"size": 10}, bgcolor="rgba(128,128,128,0.35)", borderpad=1)
    return new_height
