import { categoryBars, columnChart } from '../charts.js';
import { modelColor } from '../data.js';
import { html, mean, num, pct, raw, rolling, toneClass } from '../format.js';
import { dataTable } from '../table.js';
import { panel } from './parts.js';

export default {
  title: 'Diagnostics',
  subtitle: (ctx) => `Ranking quality of ${ctx.index.labels[ctx.model]}, measured as ranks, not price accuracy`,
  render(ctx) {
    const { index, model } = ctx;
    const periods = index.periods[model];
    const s = index.summaries[model];
    const ic = periods.map((row) => row.rank_ic);
    const quintiles = [1, 2, 3, 4, 5].map((q) => mean(periods.map((row) => row[`q${q}_return`])));
    const monotone = quintiles.every((value, i) => i === 0 || value <= quintiles[i - 1]);

    // IC histogram with fixed 0.05-wide bins, centred on zero.
    const edges = [];
    for (let edge = -0.4; edge <= 0.4001; edge += 0.05) edges.push(Number(edge.toFixed(2)));
    const counts = edges.slice(0, -1).map((lo, i) => ic.filter((value) => value >= lo && (i === edges.length - 2 ? value <= edges[i + 1] : value < edges[i + 1])).length);
    const outside = ic.filter((value) => value < edges[0] || value > edges.at(-1)).length;

    ctx.el.innerHTML = html`
      <div class="kpis">
        <div class="kpi"><div class="label">Mean Rank IC</div><div class="value">${num(s.mean_rank_ic, 3)}</div><div class="sub">IC volatility ${num(s.ic_volatility, 3)}</div></div>
        <div class="kpi"><div class="label">IC information ratio</div><div class="value">${num(s.ic_information_ratio, 2)}</div><div class="sub">t-stat ${num(s.ic_t_stat, 2)} over ${s.folds} folds</div></div>
        <div class="kpi"><div class="label">Positive IC months</div><div class="value">${pct(s.positive_ic_rate, 0)}</div><div class="sub">50% is a coin flip</div></div>
        <div class="kpi"><div class="label">Q1 − Q5 spread</div><div class="value ${toneClass(s.mean_q1_q5_spread)}">${pct(s.mean_q1_q5_spread, 2)}</div><div class="sub">Per 20-session period, vs sector</div></div>
        <div class="kpi"><div class="label">Quintile ordering</div><div class="value">${monotone ? 'Monotone' : 'Not monotone'}</div><div class="sub">On average across folds</div></div>
      </div>
      ${raw(panel({ title: 'Rank IC by rebalance', note: 'Spearman correlation between the score and the realised sector-relative return in each month. The line is the 12-month rolling mean.', body: '<div id="ic"></div>' }))}
      <div class="grid cols-2 section-gap">
        ${raw(panel({ title: 'Average return by quintile', note: 'Mean realised 20-session return relative to sector. With predictive power, Q1 > Q2 > … > Q5.', body: '<div id="quintiles"></div>' }))}
        ${raw(panel({ title: 'Distribution of monthly IC', note: `Bins of 0.05.${outside ? ` ${outside} month(s) fall outside ±0.40.` : ''}`, body: '<div id="hist"></div>' }))}
      </div>
      <div class="section-gap">${raw(panel({ title: 'Performance by market regime', note: 'Each month is labelled with trailing information only: 63-session market return sets expansion or contraction; 20-session market volatility above the training-window median sets high vol. These are diagnostics, not tuning targets.', body: '<div id="regimes"></div>', flush: true }))}</div>`;

    const color = modelColor(model);
    columnChart(document.getElementById('ic'), {
      dates: periods.map((row) => row.date), values: ic, height: 260,
      yFormat: (value) => value.toFixed(2), positive: color, negative: 'var(--neg)',
      overlay: { label: '12M rolling mean', values: rolling(ic, 12), color: 'var(--ink)' },
      label: 'Monthly Rank IC with a twelve-month rolling mean',
      tooltipRows: (i) => [
        { label: 'Rank IC', value: num(ic[i], 3) },
        { label: '12M mean', value: num(rolling(ic, 12)[i], 3) },
        { label: 'Q1 − Q5', value: pct(periods[i].q1_q5_spread, 2) },
        { label: 'Regime', value: periods[i].regime },
      ],
    });
    categoryBars(document.getElementById('quintiles'), {
      labels: ['Q1 top', 'Q2', 'Q3', 'Q4', 'Q5 bottom'], values: quintiles,
      colors: quintiles.map((value) => (value >= 0 ? color : 'var(--neg)')),
      yFormat: (value) => pct(value, 2), label: 'Average sector-relative return by quintile',
      tooltipRows: (i) => [{ label: 'Mean relative return', value: pct(quintiles[i], 3) }, { label: 'Months above zero', value: pct(periods.filter((row) => row[`q${i + 1}_return`] > 0).length / periods.length, 0) }],
    });
    categoryBars(document.getElementById('hist'), {
      labels: edges.slice(0, -1).map((lo) => (Math.abs(lo) < 1e-9 ? '0' : lo.toFixed(2).replace('0.', '.'))),
      values: counts, colors: edges.slice(0, -1).map((lo) => (lo >= 0 ? color : 'var(--neg)')),
      yFormat: (value) => String(Math.round(value)), label: 'Histogram of monthly Rank IC',
      tooltipRows: (i) => [{ label: 'Range', value: `${edges[i].toFixed(2)} to ${edges[i + 1].toFixed(2)}` }, { label: 'Months', value: String(counts[i]) }],
    });
    dataTable(document.getElementById('regimes'), {
      rows: index.regimes[model], sortKey: 'folds',
      columns: [
        { key: 'regime', label: 'Regime' },
        { key: 'folds', label: 'Months', num: true },
        { key: 'mean_rank_ic', label: 'Mean IC', num: true, render: (row) => html`<span class="${toneClass(row.mean_rank_ic)}">${num(row.mean_rank_ic, 3)}</span>` },
        { key: 'positive_ic_rate', label: 'IC > 0', num: true, render: (row) => pct(row.positive_ic_rate, 0) },
        { key: 'mean_q1_q5_spread', label: 'Q1 − Q5', num: true, render: (row) => pct(row.mean_q1_q5_spread, 2) },
        { key: 'mean_net_return', label: 'Sleeve net', num: true, render: (row) => pct(row.mean_net_return, 2) },
        { key: 'mean_benchmark_return', label: 'Universe', num: true, render: (row) => pct(row.mean_benchmark_return, 2) },
      ],
    });
  },
};
