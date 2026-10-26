"""
Corporate bar charts for the monthly consumption / cost matrices produced by `analytics.py`.

matplotlib only (Agg canvas, no pyplot global state, so it is safe in Streamlit threads and Celery workers).
Returns PNG bytes in an `io.BytesIO`, or None when there is nothing to draw (callers then simply omit the chart).

Chart type is decided by the data, never by a flag:
- more than one year  -> grouped bars, one colour per year (month-by-month comparison);
- one year, several dimensions (POD, plate, utility type...) -> stacked bars, one colour per dimension;
- otherwise -> plain bars.
Months without data have no bar (they are not drawn as zero).
"""
import io
from typing import List, Optional, Sequence, Tuple

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from app.reporting.analytics import MONTH_ABBR, MetricMatrix, format_it

# inambiente identity: main green, corporate dark green, blue-grey, neutral grey, then lighter tints
PALETTE: Tuple[str, ...] = ("#8CC63F", "#1E4D2B", "#6B8BA4", "#9AA5A0", "#BFE08A", "#3F7A4F", "#A9BCCB", "#5E6B64")
TEXT_COLOR = "#33403A"
GRID_COLOR = "#E3E8E2"
DEFAULT_FIGSIZE = (10.0, 4.6)
DEFAULT_DPI = 150


def _decimals(values: Sequence[float]) -> int:
    top = max((abs(v) for v in values), default=0)
    return 0 if top >= 100 else (1 if top >= 10 else 2)


def _bars(matrix: MetricMatrix) -> Tuple[List[Tuple[str, Sequence[Optional[float]]]], bool]:
    """(series to draw as (legend name, 12 values), stacked?)"""
    if len(matrix.years) > 1:
        return [(str(y), matrix.total.values[y]) for y in matrix.years], False
    if len(matrix.by_dimension) > 1:
        y = matrix.years[0]
        return [(s.name, s.values[y]) for s in matrix.by_dimension], True
    y = matrix.years[0]
    return [(str(y), matrix.total.values[y])], False


def render_monthly_chart(
    matrix: MetricMatrix,
    title: Optional[str] = None,
    dpi: int = DEFAULT_DPI,
    figsize: Tuple[float, float] = DEFAULT_FIGSIZE,
) -> Optional[io.BytesIO]:
    if not matrix.years or not any(v is not None for y in matrix.years for v in matrix.total.values[y]):
        return None

    series, stacked = _bars(matrix)
    unit = f" ({matrix.unit})" if matrix.unit else ""
    dec = _decimals([v for _, vals in series for v in vals if v is not None])

    fig = Figure(figsize=figsize, dpi=dpi, facecolor="white")
    FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)
    ax.set_facecolor("white")
    x = list(range(12))
    n = len(series)
    width = 0.78 if stacked or n == 1 else 0.8 / n
    rotate = not stacked and n * 12 > 24
    label_size = 6.5 if rotate else 7.5

    top = 0.0
    if stacked:
        bottoms = [0.0] * 12
        for k, (name, vals) in enumerate(series):
            heights = [v if v is not None else 0.0 for v in vals]
            ax.bar(x, heights, width, bottom=bottoms, label=name, color=PALETTE[k % len(PALETTE)], edgecolor="white", linewidth=0.5)
            bottoms = [b + h for b, h in zip(bottoms, heights)]
        for xi, (b, any_data) in enumerate(zip(bottoms, [any(vals[i] is not None for _, vals in series) for i in range(12)])):
            if any_data:
                ax.annotate(format_it(b, dec), (xi, b), ha="center", va="bottom", xytext=(0, 2), textcoords="offset points",
                            fontsize=label_size, color=TEXT_COLOR)
                top = max(top, b)
    else:
        for k, (name, vals) in enumerate(series):
            offset = (k - (n - 1) / 2) * width
            xs = [xi + offset for xi, v in enumerate(vals) if v is not None]
            hs = [v for v in vals if v is not None]
            ax.bar(xs, hs, width * 0.92, label=name, color=PALETTE[k % len(PALETTE)], edgecolor="white", linewidth=0.5)
            for xv, hv in zip(xs, hs):
                ax.annotate(format_it(hv, dec), (xv, hv), ha="center", va="bottom" if hv >= 0 else "top",
                            xytext=(0, 2 if hv >= 0 else -2), textcoords="offset points", fontsize=label_size,
                            color=TEXT_COLOR, rotation=90 if rotate else 0)
                top = max(top, hv)

    lows = [v for _, vals in series for v in vals if v is not None]
    bottom = min(0.0, min(lows)) if lows else 0.0
    span = (top - bottom) or 1.0
    ax.set_ylim(bottom * 1.15 if bottom < 0 else 0, top + span * (0.22 if rotate else 0.12))
    ax.set_xticks(x)
    ax.set_xticklabels(MONTH_ABBR, fontsize=9, color=TEXT_COLOR)
    ax.tick_params(axis="y", labelsize=8.5, colors=TEXT_COLOR)
    ax.yaxis.set_major_formatter(lambda v, _pos: format_it(v, 0))
    ax.set_ylabel(f"{matrix.label}{unit}", fontsize=9.5, color=TEXT_COLOR)
    ax.set_title(title or f"{matrix.label}{unit}", fontsize=12, fontweight="bold", color=PALETTE[1], loc="left", pad=12)
    ax.grid(axis="y", color=GRID_COLOR, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID_COLOR)
    if n > 1 or stacked:
        ax.legend(fontsize=8.5, frameon=False, ncols=min(n, 6), loc="lower right", bbox_to_anchor=(1.0, 1.0))

    fig.tight_layout()
    out = io.BytesIO()
    fig.savefig(out, format="png", dpi=dpi, facecolor="white")
    out.seek(0)
    return out
