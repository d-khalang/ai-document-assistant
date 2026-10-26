"""
Corporate bar charts for the monthly consumption / cost matrices produced by `analytics.py`.

matplotlib only (Agg canvas, no pyplot global state, so it is safe in Streamlit threads and Celery workers).
Returns PNG bytes in an `io.BytesIO`, or None when there is nothing to draw (callers then simply omit the chart).

Chart type is decided by the data, never by a flag:
- several years AND several dimensions (e.g. 6 vehicles over 2 years) -> per month one stack per year, each stack split by
  dimension (year printed under every stack);
- several years -> grouped bars, one colour per year (month-by-month comparison);
- one year, several dimensions (POD, plate, utility type...) -> stacked bars, one colour per dimension;
- otherwise -> plain bars.
More dimensions than palette colours would make the legend unreadable, so the dimensions are then folded into the total.
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

Values = Sequence[Optional[float]]


def _decimals(values: Sequence[float]) -> int:
    top = max((abs(v) for v in values), default=0)
    return 0 if top >= 100 else (1 if top >= 10 else 2)


def _stack(ax, xs: Sequence[float], layers: List[Tuple[str, Values]], width: float, colors: Sequence[str],
           dec: int, label_size: float, rotate: bool, legend_names: bool = True) -> Tuple[float, List[Optional[float]]]:
    """Draws one stack per x position from `layers` (name, 12 values); returns (highest total, totals per month)."""
    bottoms = [0.0] * len(xs)
    for k, (name, vals) in enumerate(layers):
        heights = [v if v is not None else 0.0 for v in vals]
        ax.bar(xs, heights, width, bottom=bottoms, label=name if legend_names else None, color=colors[k % len(colors)],
               edgecolor="white", linewidth=0.5)
        bottoms = [b + h for b, h in zip(bottoms, heights)]
    top = 0.0
    totals: List[Optional[float]] = []
    for i, (xi, b) in enumerate(zip(xs, bottoms)):
        if any(vals[i] is not None for _, vals in layers):
            ax.annotate(format_it(b, dec), (xi, b), ha="center", va="bottom", xytext=(0, 2), textcoords="offset points",
                        fontsize=label_size, color=TEXT_COLOR, rotation=90 if rotate else 0)
            top = max(top, b)
            totals.append(b)
        else:
            totals.append(None)
    return top, totals


def _finish(fig, ax, matrix: MetricMatrix, title: Optional[str], unit: str, top: float, bottom: float, rotate: bool,
            legend_entries: int) -> io.BytesIO:
    span = (top - bottom) or 1.0
    ax.set_ylim(bottom * 1.15 if bottom < 0 else 0, top + span * (0.22 if rotate else 0.12))
    ax.set_xticks(list(range(12)))
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
    if legend_entries > 1:
        ax.legend(fontsize=8.5, frameon=False, ncols=min(legend_entries, 6), loc="lower right", bbox_to_anchor=(1.0, 1.0))
    fig.tight_layout()
    out = io.BytesIO()
    fig.savefig(out, format="png", dpi=fig.dpi, facecolor="white")
    out.seek(0)
    return out


def _render_year_stacks(fig, ax, matrix: MetricMatrix, title: Optional[str], unit: str) -> io.BytesIO:
    """Per month: one stack per year, each split by dimension; the year is written under every stack."""
    years = list(matrix.years)
    n = len(years)
    width = 0.8 / n
    dec = _decimals([v for s in matrix.by_dimension for y in years for v in s.values[y] if v is not None])
    top = 0.0
    minor_x: List[float] = []
    minor_labels: List[str] = []
    for k, y in enumerate(years):
        offset = (k - (n - 1) / 2) * width
        xs = [i + offset for i in range(12)]
        layers = [(s.name, s.values[y]) for s in matrix.by_dimension]
        stack_top, totals = _stack(ax, xs, layers, width * 0.92, PALETTE, dec, 6.5, rotate=True, legend_names=(k == 0))
        top = max(top, stack_top)
        for xi, tot in zip(xs, totals):
            if tot is not None:
                minor_x.append(xi)
                minor_labels.append(str(y))
    ax.set_xticks(minor_x, minor=True)
    ax.set_xticklabels(minor_labels, minor=True, fontsize=6, color=TEXT_COLOR, rotation=90)
    ax.tick_params(axis="x", which="minor", length=0, pad=2)
    ax.tick_params(axis="x", which="major", length=0, pad=22)
    return _finish(fig, ax, matrix, title, unit, top, 0.0, True, len(matrix.by_dimension))


def render_monthly_chart(
    matrix: MetricMatrix,
    title: Optional[str] = None,
    dpi: int = DEFAULT_DPI,
    figsize: Tuple[float, float] = DEFAULT_FIGSIZE,
) -> Optional[io.BytesIO]:
    if not matrix.years or not any(v is not None for y in matrix.years for v in matrix.total.values[y]):
        return None

    unit = f" ({matrix.unit})" if matrix.unit else ""
    fig = Figure(figsize=figsize, dpi=dpi, facecolor="white")
    FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)
    ax.set_facecolor("white")

    if len(matrix.years) > 1 and 1 < len(matrix.by_dimension) <= len(PALETTE):
        return _render_year_stacks(fig, ax, matrix, title, unit)

    x = list(range(12))
    if len(matrix.years) > 1:                                         # grouped by year on the total
        series: List[Tuple[str, Values]] = [(str(y), matrix.total.values[y]) for y in matrix.years]
        stacked = False
    elif 1 < len(matrix.by_dimension) <= len(PALETTE):                # one year, stacked by dimension
        y = matrix.years[0]
        series = [(s.name, s.values[y]) for s in matrix.by_dimension]
        stacked = True
    else:
        y = matrix.years[0]
        series = [(str(y), matrix.total.values[y])]
        stacked = False

    n = len(series)
    dec = _decimals([v for _, vals in series for v in vals if v is not None])
    width = 0.78 if stacked or n == 1 else 0.8 / n
    rotate = not stacked and n * 12 > 24
    label_size = 6.5 if rotate else 7.5

    top = 0.0
    if stacked:
        top, _ = _stack(ax, x, series, width, PALETTE, dec, label_size, rotate=False)
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
    return _finish(fig, ax, matrix, title, unit, top, bottom, rotate, n if (n > 1 or stacked) else 0)
