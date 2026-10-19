import plotly.graph_objects as go
import math


def make_gauge(label, value, target, red_flag, higher_is_better, show_label=True):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None

    span = abs(target - red_flag)
    if higher_is_better:
        axis_min = red_flag - 0.5 * span
        axis_max = target + 0.5 * span
        midpoint = (red_flag + target) / 2.0
        steps = [
            {"range": [axis_min, red_flag], "color": "#e5202e"},
            {"range": [red_flag, midpoint], "color": "#f9a11b"},
            {"range": [midpoint, target], "color": "#5cb647"},
            {"range": [target, axis_max], "color": "#0b8a47"},
        ]
        tickvals = [axis_min, red_flag, target, axis_max]
    else:
        axis_min = target - 0.5 * span
        axis_max = red_flag + 0.5 * span
        midpoint = (target + red_flag) / 2.0
        steps = [
            {"range": [axis_min, target], "color": "#0b8a47"},
            {"range": [target, midpoint], "color": "#5cb647"},
            {"range": [midpoint, red_flag], "color": "#f9a11b"},
            {"range": [red_flag, axis_max], "color": "#e5202e"},
        ]
        tickvals = [axis_min, target, red_flag, axis_max]

    clamped_val = min(axis_max, max(axis_min, float(value)))
    ticktext = [f"{v:.2f}".rstrip("0").rstrip(".") for v in tickvals]

    fig = go.Figure(
        go.Indicator(
            mode="gauge",
            value=clamped_val,
            gauge={
                "shape": "angular",
                "bar": {"color": "rgba(0,0,0,0)"},
                "axis": {
                    "range": [axis_min, axis_max],
                    "tickvals": tickvals,
                    "ticktext": ticktext,
                },
                "steps": steps,
                "threshold": {
                    "line": {"color": "#00b4ff", "width": 10},
                    "thickness": 1.0,
                    "value": clamped_val,
                },
            },
        )
    )

    fig.update_layout(
        title={
            "text": f"{label}: {value:.2f}" if show_label else f"{value:.2f}",
            "font": {"size": 13},
            "y": 0.98,
            "yanchor": "top",
        },
        height=210,
        margin=dict(l=20, r=20, t=80, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )

    return fig
