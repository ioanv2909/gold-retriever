"""Tab-ul Burse din pagina principala: intervalele de tranzactionare ale burselor cu pozitii, in ora locala."""
from datetime import datetime, timedelta

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
        items.append((f"{'🟢' if is_open else '⚪'} {name} · {len(names)}", suffix, is_open, sorted(names)))
        table.append({t("mh.col.exchange"): name, t("mh.col.positions"): len(names),
                      t("mh.col.status"): t("mh.open") if is_open else t("mh.closed"),
                      t("mh.col.next"): (t("mh.closes") if is_open else t("mh.opens")) + " " + _fmt_wait(now, change)})
    # ordinea: dupa ora de deschidere de azi (bursele fara sesiune azi la final)
    first = {s: (mh.sessions_between(s, day_start, day_start + timedelta(days=1)) or [(day_start + timedelta(days=2),)])[0][0]
             for _, s, _, _ in items}
    order = sorted(range(len(items)), key=lambda i: (first[items[i][1]], items[i][0]))
    items = [items[i] for i in order]
    table = [table[i] for i in order]

    st.caption(t("mh.caption", tz=str(zone), d=f"{now:%d.%m.%Y}"))
    mobile.plotly_chart(_chart(items, day_start, now), width="stretch", key="mh_chart")
    st.dataframe(table, hide_index=True, width="stretch")
    if unknown:
        st.caption(t("mh.unknown", tickers=", ".join(sorted(str(x) for x in unknown))))
