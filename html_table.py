"""Tabel HTML simplu pentru listele unde st.dataframe nu ajunge: tooltip pe celula (de ex. tickerul pe nume),
sigle si legaturi care deschid pagina pozitiei (?detail=<ticker>). Fara sortare pe coloane.

coloane: dict(key, label, help=None, width=None, align="left"|"right"|"center", nowrap=False)
celule: text simplu sau dict(text=..., title=..., style=..., href=..., img=..., img_title=...)
"""
import html

import streamlit as st

_CSS = """<style>
.grtbl-wrap{overflow:auto;border:1px solid rgba(128,128,128,.25);border-radius:8px}
.grtbl{border-collapse:collapse;width:100%;font-size:14px}
.grtbl th{position:sticky;top:0;z-index:1;background:var(--gr-th-bg,rgba(128,128,128,.18));backdrop-filter:blur(6px);
  text-align:left;font-weight:600;padding:6px 8px;white-space:nowrap;border-bottom:1px solid rgba(128,128,128,.3);cursor:default}
.grtbl td{padding:5px 8px;border-bottom:1px solid rgba(128,128,128,.15);vertical-align:middle}
.grtbl tr:hover td{background:rgba(128,128,128,.10)}
.grtbl a{color:inherit;text-decoration:none}
.grtbl a:hover{text-decoration:underline}
.grtbl img.grtbl-logo{width:22px;height:22px;border-radius:5px;object-fit:contain;display:block}
.grtbl .nw{white-space:nowrap}
</style>"""


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


def build(columns, rows):
    head = "".join('<th%s%s>%s</th>' % (
        (' title="%s"' % html.escape(str(c["help"]), quote=True)) if c.get("help") else "",
        (' style="width:%s"' % html.escape(c["width"], quote=True)) if c.get("width") else "",
        html.escape(str(c.get("label") or ""))) for c in columns)
    body = "".join("<tr>%s</tr>" % "".join(_cell(r.get(c["key"]), c) for c in columns) for r in rows)
    return '<table class="grtbl"><thead><tr>%s</tr></thead><tbody>%s</tbody></table>' % (head, body)


def render(columns, rows, max_height=620):
    st.markdown(_CSS + '<div class="grtbl-wrap" style="max-height:%dpx">%s</div>' % (max_height, build(columns, rows)),
                unsafe_allow_html=True)


def detail_href(ticker):
    from urllib.parse import quote
    return "?detail=" + quote(str(ticker), safe="")
