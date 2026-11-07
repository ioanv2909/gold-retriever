import plotly.graph_objects as go

import mobile


def test_pan_on_desktop_and_fixed_on_phone(monkeypatch):
    calls = []
    monkeypatch.setattr(mobile.st, "plotly_chart", lambda fig, **kw: calls.append((fig, kw)))
    monkeypatch.setattr(mobile, "compact", lambda: False)
    mobile.plotly_chart(go.Figure(), pan=True, key="a")
    fig, kw = calls[-1]
    assert fig.layout.dragmode == "pan" and kw["config"]["scrollZoom"] is True
    assert fig.layout.yaxis.fixedrange is True
    monkeypatch.setattr(mobile, "compact", lambda: True)
    mobile.plotly_chart(go.Figure(), pan=True, key="b")
    fig, kw = calls[-1]
    assert fig.layout.dragmode is False and kw["config"]["scrollZoom"] is False
