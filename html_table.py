"""Tabel HTML pentru listele unde st.dataframe nu ajunge: tooltip pe celula (de ex. tickerul pe nume), sigle si
legaturi care deschid pagina pozitiei (?detail=<ticker>). In browser: sortare la clic pe titlul coloanei (▲/▼) si
butonul "⚙ Coloane" pentru ascunderea / afisarea coloanelor; ambele se tin minte in browser, per tabel.

coloane: dict(key, label, help=None, width=None, align="left"|"right"|"center", nowrap=False, sortable=True)
celule: text simplu sau dict(text=..., title=..., style=..., href=..., img=..., img_title=..., sort=...)
        sort = valoarea dupa care se sorteaza (numar sau text, de ex. data ISO); implicit textul afisat.
"""
import html

import streamlit as st

_CSS = """<style>
.grtbl-wrap{overflow:auto;border:1px solid rgba(128,128,128,.25);border-radius:8px}
.grtbl{border-collapse:collapse;width:100%;font-size:14px}
.grtbl th{position:sticky;top:0;z-index:1;background:var(--gr-th-bg,rgba(128,128,128,.18));backdrop-filter:blur(6px);
  text-align:left;font-weight:600;padding:6px 8px;white-space:nowrap;border-bottom:1px solid rgba(128,128,128,.3);
  cursor:default;user-select:none}
.grtbl th[data-sortable="1"]{cursor:pointer}
.grtbl th[data-sortable="1"]:hover{background:rgba(128,128,128,.28)}
.grtbl td{padding:5px 8px;border-bottom:1px solid rgba(128,128,128,.15);vertical-align:middle}
.grtbl tr:hover td{background:rgba(128,128,128,.10)}
.grtbl a{color:inherit;text-decoration:none}
.grtbl a:hover{text-decoration:underline}
.grtbl img.grtbl-logo{width:22px;height:22px;border-radius:5px;object-fit:contain;display:block}
.grtbl .nw{white-space:nowrap}
.grtbl-bar{display:flex;justify-content:flex-end;margin:0 0 4px}
.grtbl-cols{position:relative;font-size:13px}
.grtbl-cols summary{cursor:pointer;list-style:none;padding:2px 8px;border:1px solid rgba(128,128,128,.35);border-radius:6px}
.grtbl-cols summary::-webkit-details-marker{display:none}
.grtbl-colbox{position:absolute;right:0;z-index:5;margin-top:4px;padding:8px 10px;max-height:320px;overflow:auto;
  background:var(--background-color,#1e1e1e);border:1px solid rgba(128,128,128,.35);border-radius:8px;
  box-shadow:0 4px 14px rgba(0,0,0,.3);display:flex;flex-direction:column;gap:4px;white-space:nowrap}
.grtbl-colbox label{cursor:pointer}
</style>"""

# Comportamentul din browser (sortare + alegerea coloanelor), aplicat tuturor tabelelor .grtbl inca neinitializate.
_JS = r"""
(function () {
  function cellValue(row, i) {
    const c = row.cells[i];
    if (!c) return "";
    const raw = (c.dataset.sort !== undefined ? c.dataset.sort : c.textContent).trim();
    const num = raw.replace(/\s/g, "").replace(/%$/, "").replace(/\/100$/, "");
    if (/^[-+]?\d+(\.\d+)?$/.test(num)) return parseFloat(num);
    return raw.toLowerCase();
  }
  function init() {
    document.querySelectorAll("table.grtbl[data-tid]").forEach(function (tb) {
      if (tb.dataset.ready) return;
      tb.dataset.ready = "1";
      const key = "grtbl:" + tb.dataset.tid;
      let state = {};
      try { state = JSON.parse(localStorage.getItem(key) || "{}"); } catch (e) { state = {}; }
      const save = function () { try { localStorage.setItem(key, JSON.stringify(state)); } catch (e) {} };
      const ths = Array.from(tb.tHead.rows[0].cells);
      const body = tb.tBodies[0];
      const apply = function () {
        const hidden = new Set(state.hidden || []);
        ths.forEach(function (th, i) {
          const show = !hidden.has(th.dataset.key);
          th.style.display = show ? "" : "none";
          Array.from(body.rows).forEach(function (r) { if (r.cells[i]) r.cells[i].style.display = show ? "" : "none"; });
        });
      };
      const sortBy = function (i, dir) {
        const rows = Array.from(body.rows);
        rows.sort(function (a, b) {
          const x = cellValue(a, i), y = cellValue(b, i);
          const ex = x === "" || x === "—" || x === "n/a", ey = y === "" || y === "—" || y === "n/a";
          if (ex || ey) return ex === ey ? 0 : (ex ? 1 : -1);
          if (typeof x !== typeof y) return (typeof x === "number" ? -1 : 1) * dir;
          return (x < y ? -1 : x > y ? 1 : 0) * dir;
        });
        rows.forEach(function (r) { body.appendChild(r); });
        ths.forEach(function (t) { const a = t.querySelector(".grtbl-arrow"); if (a) a.remove(); });
        const arrow = document.createElement("span");
        arrow.className = "grtbl-arrow";
        arrow.textContent = dir > 0 ? " ▲" : " ▼";
        ths[i].appendChild(arrow);
      };
      ths.forEach(function (th, i) {
        if (th.dataset.sortable !== "1") return;
        th.addEventListener("click", function () {
          const dir = state.sort && state.sort.key === th.dataset.key ? -state.sort.dir : 1;
          state.sort = { key: th.dataset.key, dir: dir };
          save();
          sortBy(i, dir);
        });
      });
      if (state.sort) {
        const i = ths.findIndex(function (t) { return t.dataset.key === state.sort.key; });
        if (i >= 0) sortBy(i, state.sort.dir);
      }
      const wrap = tb.closest(".grtbl-wrap");
      if (wrap && !(wrap.previousElementSibling && wrap.previousElementSibling.classList.contains("grtbl-bar"))) {
        const bar = document.createElement("div");
        bar.className = "grtbl-bar";
        const det = document.createElement("details");
        det.className = "grtbl-cols";
        const sum = document.createElement("summary");
        sum.textContent = "⚙ " + (tb.dataset.colsLabel || "Columns");
        det.appendChild(sum);
        const box = document.createElement("div");
        box.className = "grtbl-colbox";
        ths.forEach(function (th) {
          if (!th.dataset.label) return;
          const lab = document.createElement("label");
          const cb = document.createElement("input");
          cb.type = "checkbox";
          cb.checked = !(state.hidden || []).includes(th.dataset.key);
          cb.addEventListener("change", function () {
            const h = new Set(state.hidden || []);
            if (cb.checked) h.delete(th.dataset.key); else h.add(th.dataset.key);
            state.hidden = Array.from(h);
            save();
            apply();
          });
          lab.appendChild(cb);
          lab.appendChild(document.createTextNode(" " + th.dataset.label));
          box.appendChild(lab);
        });
        det.appendChild(box);
        bar.appendChild(det);
        wrap.parentNode.insertBefore(bar, wrap);
      }
      apply();
    });
  }
  init();
  setTimeout(init, 300);
  setTimeout(init, 1200);
})();
"""


def _cell(value, col):
    if not isinstance(value, dict):
        value = {"text": value}
    text = value.get("text")
    text = "" if text is None else str(text)
    inner = html.escape(text)
    if value.get("img"):
        inner = '<img class="grtbl-logo" src="%s" alt="" title="%s">' % (
            html.escape(value["img"], quote=True), html.escape(str(value.get("img_title") or ""), quote=True)) + inner
    if value.get("href"):
        inner = '<a href="%s" target="_self">%s</a>' % (html.escape(value["href"], quote=True), inner)
    attrs = []
    if value.get("title"):
        attrs.append('title="%s"' % html.escape(str(value["title"]), quote=True))
    if value.get("sort") is not None:
        attrs.append('data-sort="%s"' % html.escape(str(value["sort"]), quote=True))
    style = []
    if col.get("align"):
        style.append("text-align:%s" % col["align"])
    if col.get("width"):
        style.append("width:%s" % col["width"])
    if value.get("style"):
        style.append(value["style"])
    if style:
        attrs.append('style="%s"' % html.escape(";".join(style), quote=True))
    cls = ' class="nw"' if col.get("nowrap") else ""
    return "<td%s%s>%s</td>" % (cls, (" " + " ".join(attrs)) if attrs else "", inner)


def build(columns, rows, tid=None, cols_label="Coloane"):
    head = "".join('<th data-key="%s" data-label="%s" data-sortable="%s"%s%s>%s</th>' % (
        html.escape(str(c["key"]), quote=True), html.escape(str(c.get("label") or ""), quote=True),
        "1" if c.get("sortable", True) and c.get("label") else "0",
        (' title="%s"' % html.escape(str(c["help"]), quote=True)) if c.get("help") else "",
        (' style="width:%s"' % html.escape(c["width"], quote=True)) if c.get("width") else "",
        html.escape(str(c.get("label") or ""))) for c in columns)
    body = "".join("<tr>%s</tr>" % "".join(_cell(r.get(c["key"]), c) for c in columns) for r in rows)
    ident = (' data-tid="%s" data-cols-label="%s"' % (html.escape(str(tid), quote=True), html.escape(cols_label, quote=True))
             if tid else "")
    return '<table class="grtbl"%s><thead><tr>%s</tr></thead><tbody>%s</tbody></table>' % (ident, head, body)


def render(columns, rows, tid=None, max_height=620):
    """tid: numele tabelului (pentru sortarea si coloanele tinute minte); fara el, tabelul e static."""
    from i18n import t
    st.markdown(_CSS + '<div class="grtbl-wrap" style="max-height:%dpx">%s</div>'
                % (max_height, build(columns, rows, tid, t("tbl.columns"))), unsafe_allow_html=True)
    if tid:
        from appearance import _run_js
        _run_js(_JS)


def detail_href(ticker):
    from urllib.parse import quote
    return "?detail=" + quote(str(ticker), safe="")
