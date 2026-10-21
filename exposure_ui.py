"""Tab-ul Expunere din pagina principala: sector, tara, moneda."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import exposure
from i18n import t

BAR = "#2a78d6"
MAX_BARS = 12
VIEWS = ("composition", "rotation", "factors")


def _label(dim, key):
    if key == exposure.OTHER and dim == "country":
        return t("ex.bucket.other_countries")
    if key in (exposure.ETF, exposure.UNKNOWN, exposure.OTHER):
        return t("ex.bucket." + key.strip("_"))
    if dim == "sector":
        name = t("ex.sector." + key)
        return key if name.startswith("ex.sector.") else name
    return key


def _fold(items, dim):
    """Cel mult MAX_BARS bare; restul intra intr-o bara "Altele"."""
    items = [(_label(dim, k), v, p) for k, v, p in items]
    if len(items) <= MAX_BARS:
        return items
    head, tail = items[:MAX_BARS - 1], items[MAX_BARS - 1:]
    return head + [(t("ex.bucket.rest", n=len(tail)), sum(v for _, v, _ in tail), sum(p for _, _, p in tail))]


def _chart(items, ccy):
    labels = [k for k, _, _ in items]
    fig = go.Figure(go.Bar(
        y=labels, x=[p for _, _, p in items], orientation="h", marker={"color": BAR, "cornerradius": 4},
        text=[f"{p:.1f}%" for _, _, p in items], textposition="outside", cliponaxis=False,
        customdata=[v for _, v, _ in items],
        hovertemplate="%{y}: %{x:.1f}% · %{customdata:,.0f} " + ccy + "<extra></extra>"))
    fig.update_layout(height=40 + 30 * len(items), margin={"l": 10, "r": 50, "t": 10, "b": 10}, bargap=0.3,
                      xaxis={"visible": False, "range": [0, max(p for _, _, p in items) * 1.15]},
                      yaxis={"autorange": "reversed"}, showlegend=False)
    return fig


def render_exposure_tab(vdf, display_ccy):
    """vdf: randurile pozitiilor din portofoliile selectate (ticker, value_disp, currencyCode)."""
    if vdf is None or vdf.empty:
        st.info(t("ex.empty"))
        return
    rows = [{"ticker": r["ticker"], "value": r.get("value_disp"), "currency": r.get("currencyCode")}
            for r in vdf.to_dict("records") if r.get("ticker")]
    meta = exposure.load_cache()
    status = exposure.load_status()
    isins = {r["ticker"]: r.get("isin") for r in vdf.to_dict("records") if r.get("ticker") and r.get("isin")}
    missing = [r["ticker"] for r in rows if r["ticker"] not in meta]
    # vederea sta in URL (?ex_view=rotation); copia de rezerva o reface cand tab-ul se redeschide
    if "ex_view" not in st.session_state and "ex_view" not in st.query_params and st.session_state.get("_saved_ex_view"):
        st.session_state["ex_view"] = st.session_state["_saved_ex_view"]
    view = st.segmented_control(t("ex.view"), VIEWS, key="ex_view", bind="query-params", default="composition",
                                format_func=lambda k: t("ex.view." + k), label_visibility="collapsed") or "composition"
    st.session_state["_saved_ex_view"] = view
    if status.get("in_progress"):
        st.caption(t("ex.loading", done=status.get("done", 0), total=status.get("total", 0)))
    elif missing and st.button(t("ex.fetch", n=len(missing)), key="ex_fetch"):
        exposure.start_fetch_background(missing, isins)
        st.rerun()
    if view != "composition":
        import portfolio_lenses_ui
        if view == "rotation":
            portfolio_lenses_ui.render_rotation(rows, meta)
        else:
            portfolio_lenses_ui.render_factors(vdf)
        return

    cols = st.columns(3)
    for col, dim in zip(cols, exposure.DIMENSIONS):
        with col:
            st.markdown("**" + t("ex.title." + dim) + "**")
            items = exposure.breakdown(rows, meta, dim)
            if not items:
                st.caption(t("ex.no_data"))
                continue
            items = _fold(items, dim)
            st.plotly_chart(_chart(items, display_ccy), width="stretch", key="ex_chart_" + dim)
            with st.expander(t("ex.table")):
                st.dataframe(pd.DataFrame([{
                    t("ex.col.category"): k, t("ex.col.value", ccy=display_ccy): round(v, 2), "%": round(p, 1),
                } for k, v, p in items]), hide_index=True, width="stretch")
    st.caption(t("ex.note"))
