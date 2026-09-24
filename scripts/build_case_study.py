"""Render the portfolio case-study page from the default workspace.

Every number and chart on the page comes from src/alphacast/snapshots/default_run.json.gz,
so the write-up cannot drift from what the live app shows.

    python scripts/build_case_study.py ../../nathan-portfolio/public/Project-AlphaCast.dc.html
"""

from __future__ import annotations

import gzip
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "src" / "alphacast" / "snapshots" / "default_run.json.gz"
STYLE_SOURCE = "Project-Quant-Portfolio.dc.html"  # shared case-study stylesheet

LABELS = {
    "momentum": "Momentum 12-1",
    "ridge": "Ridge",
    "elastic_net": "Elastic Net",
    "random_forest": "Random Forest",
    "gradient_boosting": "Gradient Boosting",
}
COLORS = {  # same fixed categorical order as the app
    "momentum": "#2a78d6",
    "ridge": "#eb6834",
    "elastic_net": "#1baf7a",
    "random_forest": "#c98500",
    "gradient_boosting": "#e87ba4",
}


def pct(value: float, digits: int = 1, sign: bool = False) -> str:
    text = f"{value * 100:.{digits}f}%"
    if value < 0:
        return "&minus;" + text.lstrip("-")
    return ("+" if sign and value > 0 else "") + text


def cumulative(returns: list[float]) -> list[float]:
    wealth, out = 1.0, [1.0]
    for value in returns:
        wealth *= 1 + value
        out.append(wealth)
    return out


def line_chart(series: list[dict], dates: list[str], *, y_format, label: str, baseline=None, log=False) -> str:
    """Static SVG in the case-study idiom: hairline grid, mono axis labels, 2px lines."""
    import math

    width, height, left, right, top, bottom = 760, 330, 62, 700, 16, 296
    transform = (lambda v: math.log(v)) if log else (lambda v: v)
    values = [transform(v) for s in series for v in s["values"]]
    lo, hi = min(values), max(values)
    if baseline is not None:
        lo, hi = min(lo, transform(baseline)), max(hi, transform(baseline))
    pad = (hi - lo) * 0.05
    lo, hi = lo - pad, hi + pad

    def sx(i: int) -> float:
        return left + i / (len(dates) - 1) * (right - left)

    def sy(v: float) -> float:
        return bottom - (transform(v) - lo) / (hi - lo) * (bottom - top)

    if log:
        ticks = [t for t in (1, 2, 4, 8, 16) if lo <= math.log(t) <= hi]
    else:
        raw_step = (hi - lo) / 5
        magnitude = 10 ** math.floor(math.log10(raw_step))
        step = min(m * magnitude for m in (1, 2, 2.5, 5, 10) if m * magnitude >= raw_step)
        first = math.ceil(lo / step) * step
        ticks = [round(first + k * step, 10) for k in range(int((hi - first) / step) + 1)]
    svg_style = "width:100%;height:auto;font-family:'IBM Plex Mono',monospace"
    parts = [f'<svg viewBox="0 0 {width} {height + 24}" role="img" aria-label="{label}" style="{svg_style}">']
    for tick in ticks:
        y = sy(tick)
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{right}" y2="{y:.1f}" stroke="#e6e2db" stroke-width="1"/>')
        parts.append(f'<text x="{left - 8}" y="{y + 3.5:.1f}" text-anchor="end" font-size="10" fill="#a2a5a8">{y_format(tick)}</text>')
    years = {}
    for i, day in enumerate(dates):
        years.setdefault(day[:4], i)
    for year, i in years.items():
        if int(year) % 2 == 1 or i == 0:
            parts.append(f'<text x="{sx(i):.1f}" y="{bottom + 18}" text-anchor="middle" font-size="10" fill="#a2a5a8">{year}</text>')
    if baseline is not None:
        y = sy(baseline)
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{right}" y2="{y:.1f}" stroke="#16181a" stroke-width="1"/>')
    for s in series:
        path = " ".join(f"{'M' if i == 0 else 'L'}{sx(i):.1f},{sy(v):.1f}" for i, v in enumerate(s["values"]))
        dash = ' stroke-dasharray="5 4"' if s.get("dash") else ""
        parts.append(f'<path d="{path}" fill="none" stroke="{s["color"]}" stroke-width="{s.get("width", 2)}" stroke-linejoin="round"{dash}/>')
        last = s["values"][-1]
        parts.append(f'<text x="{right + 6}" y="{sy(last) + 3.5:.1f}" font-size="10" fill="#3d4145">{s.get("end", "")}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def legend(series: list[dict]) -> str:
    items = []
    for s in series:
        style = f"background:{s['color']}" if not s.get("dash") else f"background:repeating-linear-gradient(90deg,{s['color']} 0 5px,transparent 5px 9px)"
        items.append(f'<span><span class="swatch" style="{style}"></span>{s["label"]}</span>')
    return f'<div class="legend">{"".join(items)}</div>'


def main(output: Path) -> None:
    payload = json.loads(gzip.decompress(SNAPSHOT.read_bytes()))
    ws = payload["workspace"]
    summaries = {row["model"]: row for row in ws["summaries"]}
    monitoring = {row["model"]: row for row in ws["monitoring"]}
    periods: dict[str, list[dict]] = {}
    for row in ws["periods"]:
        periods.setdefault(row["model"], []).append(row)
    for rows in periods.values():
        rows.sort(key=lambda row: row["date"])
    regimes = [row for row in ws["regimes"] if row["model"] == "random_forest"]
    rf, mom = summaries["random_forest"], summaries["momentum"]
    rf_periods = periods["random_forest"]
    folds = len(rf_periods)
    first, last = rf_periods[0]["date"], rf_periods[-1]["date"]

    def month(day: str) -> str:
        return date.fromisoformat(day).strftime("%b %Y")

    degraded = sum(row["status"] == "degraded" for row in monitoring.values())
    calm = next(row for row in regimes if row["regime"] == "Expansion / low vol")
    stressed = [row for row in regimes if row["regime"].endswith("high vol")]
    stressed_folds = sum(row["folds"] for row in stressed)
    stressed_ic = sum(row["mean_rank_ic"] * row["folds"] for row in stressed) / stressed_folds

    dates = [rf_periods[0]["train_end"]] + [row["date"] for row in rf_periods]
    growth = [
        {"label": "Random Forest, net", "color": COLORS["random_forest"], "values": cumulative([r["net_return"] for r in rf_periods]), "end": f"${cumulative([r['net_return'] for r in rf_periods])[-1]:.1f}", "width": 2.4},
        {"label": "Momentum 12-1, net", "color": COLORS["momentum"], "values": cumulative([r["net_return"] for r in periods["momentum"]]), "end": f"${cumulative([r['net_return'] for r in periods['momentum']])[-1]:.1f}"},
        {"label": "Equal-weight universe", "color": "#7d858c", "values": cumulative([r["benchmark_return"] for r in rf_periods]), "end": f"${cumulative([r['benchmark_return'] for r in rf_periods])[-1]:.1f}", "dash": True},
    ]
    growth_svg = line_chart(growth, dates, y_format=lambda v: f"${v:g}", label="Growth of one dollar: Random Forest and momentum top-15 sleeves net of costs against the equal-weight universe", log=True)

    order = ["random_forest", "gradient_boosting", "elastic_net", "ridge", "momentum"]
    ic_series = []
    for model in order:
        total, values = 0.0, []
        for row in periods[model]:
            total += row["rank_ic"]
            values.append(total)
        ic_series.append({"label": LABELS[model], "color": COLORS[model], "values": values, "end": f"{values[-1]:.1f}" if model == "random_forest" else "", "width": 2.4 if model == "random_forest" else 1.6})
    ic_svg = line_chart(ic_series, [row["date"] for row in rf_periods], y_format=lambda v: f"{v:g}", label="Cumulative monthly Rank IC by model", baseline=0)

    rows_html = []
    for model in order:
        s = summaries[model]
        cls = ' class="win"' if model == "random_forest" else ""
        tag = '<span class="tag">Only significant</span>' if model == "random_forest" else ' <span style="color:#a2a5a8">(baseline)</span>' if model == "momentum" else ""
        rows_html.append(
            f"<tr{cls}><td>{LABELS[model]}{tag}</td><td>{s['mean_rank_ic']:.3f}</td><td>{s['ic_t_stat']:.2f}</td>"
            f"<td>{pct(s['positive_ic_rate'], 0)}</td><td>{pct(s['mean_q1_q5_spread'], 2)}</td><td>{s['net_sharpe']:.2f}</td>"
            f"<td>{pct(s['mean_turnover'], 0)}</td><td>{pct(s['max_drawdown'])}</td></tr>"
        )
    rows_html.append(
        f'<tr class="bench"><td>Equal-weight universe</td><td>&mdash;</td><td>&mdash;</td><td>&mdash;</td><td>&mdash;</td>'
        f"<td>{rf['benchmark_sharpe']:.2f}</td><td>&mdash;</td><td>{pct(rf['benchmark_max_drawdown'])}</td></tr>"
    )
    regime_parts = []
    for row in sorted(regimes, key=lambda row: -row["folds"]):
        highlight = ' class="win"' if row["regime"].endswith("high vol") and row["folds"] > 5 else ""
        active = pct(row["mean_net_return"] - row["mean_benchmark_return"], 2, sign=True)
        regime_parts.append(
            f"<tr{highlight}><td>{row['regime']}</td><td>{row['folds']}</td>"
            f"<td>{row['mean_rank_ic']:.3f}</td><td>{pct(row['positive_ic_rate'], 0)}</td><td>{active}</td></tr>"
        )
    regime_rows = "".join(regime_parts)

    template = (ROOT / "scripts" / "case_study_template.html").read_text()
    style_path = output.parent / STYLE_SOURCE
    style = re.search(r"<style>.*?</style>", style_path.read_text(), re.DOTALL).group(0)
    page = template.format(
        style=style,
        folds=folds,
        first=month(first),
        last=month(last),
        signal=month(ws["signal_date"]),
        rf_ic=f"{rf['mean_rank_ic']:.3f}",
        rf_t=f"{rf['ic_t_stat']:.1f}",
        rf_pos=pct(rf["positive_ic_rate"], 0),
        mom_ic=f"{mom['mean_rank_ic']:.3f}",
        mom_t=f"{mom['ic_t_stat']:.1f}",
        rf_sharpe=f"{rf['net_sharpe']:.2f}",
        rf_gross_sharpe=f"{rf['gross_sharpe']:.2f}",
        bench_sharpe=f"{rf['benchmark_sharpe']:.2f}",
        mom_sharpe=f"{mom['net_sharpe']:.2f}",
        rf_ann=pct(rf["annualized_net_return"]),
        bench_ann=pct(rf["annualized_benchmark_return"]),
        ann_gap=f"{(rf['annualized_net_return'] - rf['annualized_benchmark_return']) * 100:.1f}",
        rf_dd=pct(rf["max_drawdown"]),
        bench_dd=pct(rf["benchmark_max_drawdown"]),
        dd_gap=f"{abs(rf['max_drawdown'] - rf['benchmark_max_drawdown']) * 100:.1f}",
        rf_turnover=pct(rf["mean_turnover"], 0),
        rf_cost=pct(rf["annualized_cost_drag"], 2),
        rf_ir=f"{rf['information_ratio']:.2f}",
        degraded=degraded,
        calm_folds=calm["folds"],
        calm_ic=f"{calm['mean_rank_ic']:.3f}",
        stressed_folds=stressed_folds,
        stressed_ic=f"{stressed_ic:.3f}",
        rf_recent=f"{monitoring['random_forest']['recent_mean_rank_ic']:.3f}",
        growth_legend=legend(growth),
        growth_svg=growth_svg,
        ic_legend=legend(ic_series),
        ic_svg=ic_svg,
        result_rows="\n".join(rows_html),
        regime_rows=regime_rows,
    )
    output.write_text(page)
    print(f"Wrote {output} ({len(page) / 1000:.0f} kB)")


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve())
