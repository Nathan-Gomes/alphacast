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
    "ensemble": "Ensemble",
}
COLORS = {  # same fixed categorical order as the app
    "momentum": "#2a78d6",
    "ridge": "#eb6834",
    "elastic_net": "#1baf7a",
    "random_forest": "#c98500",
    "gradient_boosting": "#e87ba4",
    "ensemble": "#4a3aa7",
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


def line_chart(
    series: list[dict], dates: list[str], *, y_format, label: str, baseline=None, log=False,
    x_ticks: list[tuple[int, str]] | None = None,
) -> str:
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
        parts.append(f'<text x="{left - 8}" y="{y + 3.5:.1f}" text-anchor="end" font-size="10" fill="#686c71">{y_format(tick)}</text>')
    if x_ticks is None:
        years: dict[str, int] = {}
        for i, day in enumerate(dates):
            years.setdefault(day[:4], i)
        x_ticks = [(i, year) for year, i in years.items() if int(year) % 2 == 1 or i == 0]
    for i, text in x_ticks:
        parts.append(f'<text x="{sx(i):.1f}" y="{bottom + 18}" text-anchor="middle" font-size="10" fill="#686c71">{text}</text>')
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


def _random_forest_variant(end: str, **options) -> dict:
    """Random Forest on the same snapshot with one portfolio option changed."""
    from alphacast.config import ResearchConfig
    from alphacast.data import snapshot_prices
    from alphacast.research import run_research

    run = run_research(
        snapshot_prices(), source="snapshot",
        config=ResearchConfig(end=end, models=("random_forest",), **options),
    )
    return run.summaries.iloc[0].to_dict()


def _and_list(items: list[str]) -> str:
    """'a', 'a and b', 'a, b and c'."""
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _test_count() -> int:
    """Collected pytest cases, so the page never quotes a stale number."""
    import subprocess

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"], cwd=ROOT, capture_output=True, text=True, check=False,
    )
    match = re.search(r"(\d+) tests? collected", result.stdout)
    return int(match.group(1)) if match else 0


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
        {"label": f"Universe at Random Forest's beta ({rf['beta']:.2f}x)", "color": "#b4b8bc", "values": cumulative([rf["beta"] * r["benchmark_return"] for r in rf_periods]), "end": f"${cumulative([rf['beta'] * r['benchmark_return'] for r in rf_periods])[-1]:.1f}", "dash": True},
    ]
    growth_svg = line_chart(growth, dates, y_format=lambda v: f"${v:g}", label="Growth of one dollar: Random Forest and momentum top-15 sleeves net of costs against the equal-weight universe", log=True)

    order = [m for m in ["random_forest", "ensemble", "gradient_boosting", "elastic_net", "ridge", "momentum"] if m in summaries]
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
        tag = {
            "random_forest": '<span class="tag">Strongest</span>',
            "momentum": ' <span style="color:#686c71">(baseline)</span>',
            "ensemble": ' <span style="color:#686c71">(declared in advance)</span>',
        }.get(model, "")
        rows_html.append(
            f"<tr{cls}><td>{LABELS[model]}{tag}</td><td>{s['mean_rank_ic']:.3f}</td><td>{s['ic_t_stat']:.2f}</td><td>{s['p_value_holm']:.2f}</td>"
            f"<td>{pct(s['positive_ic_rate'], 0)}</td><td>{pct(s['mean_q1_q5_spread'], 2)}</td><td>{s['net_sharpe']:.2f}</td>"
            f"<td>{pct(s['mean_turnover'], 0)}</td><td>{pct(s['max_drawdown'])}</td></tr>"
        )
    rows_html.append(
        f'<tr class="bench"><td>Equal-weight universe</td><td>&mdash;</td><td>&mdash;</td><td>&mdash;</td><td>&mdash;</td><td>&mdash;</td>'
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

    # Costs: net Sharpe rebuilt from gross returns and turnover at each one-way cost.
    def sharpe(values: list[float]) -> float:
        mean = sum(values) / len(values)
        sd = (sum((v - mean) ** 2 for v in values) / (len(values) - 1)) ** 0.5
        return (12 ** 0.5) * mean / sd if sd else 0.0

    def net_at(rows: list[dict], bps: float) -> list[float]:
        return [r["gross_return"] - r["turnover"] * bps / 10_000 for r in rows]

    bench_sharpe = sharpe([r["benchmark_return"] for r in rf_periods])
    grid = list(range(0, 105, 5))
    cost_series = [
        {"label": "Random Forest, net Sharpe", "color": COLORS["random_forest"], "values": [sharpe(net_at(rf_periods, b)) for b in grid], "width": 2.4},
        {"label": "Momentum 12-1, net Sharpe", "color": COLORS["momentum"], "values": [sharpe(net_at(periods["momentum"], b)) for b in grid]},
        {"label": "Universe Sharpe", "color": "#7d858c", "values": [bench_sharpe] * len(grid), "dash": True},
    ]
    cost_svg = line_chart(
        cost_series, [str(b) for b in grid], y_format=lambda v: f"{v:.2f}",
        label="Net Sharpe ratio against one-way trading cost from 0 to 100 basis points",
        x_ticks=[(i, f"{b} bps") for i, b in enumerate(grid) if b % 20 == 0],
    )
    rf_even = next((b for b in range(1001) if sharpe(net_at(rf_periods, b)) <= bench_sharpe), None)
    cross = next((b for b in range(1001) if sharpe(net_at(rf_periods, b)) <= sharpe(net_at(periods["momentum"], b))), None)
    mom_even = next((b for b in range(1001) if sharpe(net_at(periods["momentum"], b)) <= bench_sharpe), None)

    sector_rows = sorted((row for row in ws.get("sectors", []) if row["model"] == "random_forest"), key=lambda row: -row["mean_active_weight"])
    sector_parts = []
    for i, row in enumerate(sector_rows):
        highlight = ' class="win"' if i < 2 else ""
        sector_parts.append(
            f"<tr{highlight}><td>{row['sector']}</td><td>{row['names']}</td><td>{row['mean_rank_ic']:.3f}</td>"
            f"<td>{pct(row['positive_ic_rate'], 0)}</td><td>{pct(row['mean_active_weight'], 1, sign=True)}</td></tr>"
        )
    sector_html = "".join(sector_parts)
    top_sector = sector_rows[0] if sector_rows else None
    decay = ws.get("decay", [])
    horizons = sorted({row["horizon"] for row in decay})
    decay_models = [m for m in ("random_forest", "ensemble", "momentum") if m in summaries]
    decay_series = [
        {
            "label": LABELS[m], "color": COLORS[m], "width": 2.4 if m == "random_forest" else 1.6,
            "values": [next(r["mean_rank_ic"] for r in decay if r["model"] == m and r["horizon"] == h) for h in horizons],
            "end": "",
        }
        for m in decay_models
    ] if horizons else []
    decay_svg = line_chart(
        decay_series, [str(h) for h in horizons], y_format=lambda v: f"{v:.3f}", baseline=0,
        label="Mean Rank IC by forward horizon for Random Forest, the ensemble and momentum",
        x_ticks=[(i, f"{h} sessions") for i, h in enumerate(horizons)],
    ) if horizons else ""
    rf_decay = {r["horizon"]: r["mean_rank_ic"] for r in decay if r["model"] == "random_forest"}
    years: dict[str, list[float]] = {}
    for row in rf_periods:
        entry = years.setdefault(row["date"][:4], [1.0, 1.0, 0])
        entry[0] *= 1 + row["net_return"]
        entry[1] *= 1 + row["benchmark_return"]
        entry[2] += 1
    full_years = {y: v[0] - v[1] for y, v in years.items() if v[2] >= 12}
    rolling_betas = []
    for i in range(23, len(rf_periods)):
        window = rf_periods[i - 23 : i + 1]
        xs = [r["benchmark_return"] for r in window]
        ys = [r["net_return"] for r in window]
        mx, my = sum(xs) / 24, sum(ys) / 24
        var = sum((x - mx) ** 2 for x in xs)
        rolling_betas.append((window[-1]["date"], sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / var))
    peak_date, peak_beta = max(rolling_betas, key=lambda item: item[1])
    top_years = sorted(full_years, key=full_years.get, reverse=True)[:3]
    quarterly = _random_forest_variant(ws["config"]["end"], rebalance_every_folds=3)
    buffered = _random_forest_variant(ws["config"]["end"], hold_buffer=23)
    capped = _random_forest_variant(ws["config"]["end"], max_per_sector=2)
    neutral = _random_forest_variant(ws["config"]["end"], neutralize_volatility=True)
    tests = _test_count()

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
        rf_p=f"{rf['p_value']:.3f}",
        rf_holm=f"{rf['p_value_holm']:.2f}",
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
        cost_svg=cost_svg,
        cost_legend=legend(cost_series),
        rf_even=rf_even if rf_even is not None else "1,000+",
        mom_even=mom_even if mom_even is not None else "1,000+",
        cross=cross if cross is not None else "1,000+",
        sector_rows=sector_html,
        top_sector=top_sector["sector"] if top_sector else "",
        top_sector_weight=pct(top_sector["mean_active_weight"], 1, sign=True) if top_sector else "",
        tests=tests,
        rf_beta=f"{rf['beta']:.2f}",
        peak_beta=f"{peak_beta:.1f}",
        peak_year=peak_date[:4],
        n_ic=f"{neutral['mean_rank_ic']:.3f}",
        n_beta=f"{neutral['beta']:.2f}",
        n_alpha=pct(neutral["alpha_annualized"], 1),
        rf_alpha=pct(rf["alpha_annualized"], 1),
        rf_alpha_t=f"{rf['alpha_t_stat']:.1f}",
        mom_beta=f"{mom['beta']:.2f}",
        mom_alpha=pct(mom["alpha_annualized"], 1),
        mom_alpha_t=f"{mom['alpha_t_stat']:.1f}",
        ml_beta_range=(
            f"{min(summaries[m]['beta'] for m in summaries if m != 'momentum'):.1f} to "
            f"{max(summaries[m]['beta'] for m in summaries if m != 'momentum'):.1f}"
        ),
        years_beat=sum(v > 0 for v in full_years.values()),
        years_full=len(full_years),
        top_years=_and_list(sorted(top_years)),
        decay_svg=decay_svg,
        decay_legend=legend(decay_series) if decay_series else "",
        q_sharpe=f"{quarterly['net_sharpe']:.2f}",
        b_sharpe=f"{buffered['net_sharpe']:.2f}",
        c_sharpe_phrase=(
            f"left its net Sharpe unchanged at {capped['net_sharpe']:.2f}"
            if f"{capped['net_sharpe']:.2f}" == f"{rf['net_sharpe']:.2f}"
            else f"moved its net Sharpe from {rf['net_sharpe']:.2f} to {capped['net_sharpe']:.2f}"
        ),
        c_vol=pct(capped["annualized_volatility"]),
        c_dd=pct(capped["max_drawdown"]),
        rf_vol=pct(rf["annualized_volatility"]),
        b_turnover=pct(buffered["mean_turnover"], 0),
        q_turnover=pct(quarterly["mean_turnover"], 0),
        rf_ic10=f"{rf_decay.get(10, float('nan')):.3f}",
        rf_ic60=f"{rf_decay.get(60, float('nan')):.3f}",
        ens_ic=f"{summaries['ensemble']['mean_rank_ic']:.3f}" if "ensemble" in summaries else "n/a",
        ens_t=f"{summaries['ensemble']['ic_t_stat']:.1f}" if "ensemble" in summaries else "n/a",
        ens_sharpe=f"{summaries['ensemble']['net_sharpe']:.2f}" if "ensemble" in summaries else "n/a",
    )
    output.write_text(page)
    print(f"Wrote {output} ({len(page) / 1000:.0f} kB)")


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve())
