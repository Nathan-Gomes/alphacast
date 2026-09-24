import { categoryBars, columnChart, hbars, legend, lineChart } from '../charts.js';
import { modelColor } from '../data.js';
import { html, mean, num, pct, raw, rolling, sectorShort, toneClass } from '../format.js';
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
        <div class="kpi"><div class="label">IC information ratio</div><div class="value">${num(s.ic_information_ratio, 2)}</div><div class="sub">t ${num(s.ic_t_stat, 2)} · p ${num(s.p_value, 3)} · Holm p ${num(s.p_value_holm, 3)}</div></div>
        <div class="kpi"><div class="label">Positive IC months</div><div class="value">${pct(s.positive_ic_rate, 0)}</div><div class="sub">50% is a coin flip</div></div>
        <div class="kpi"><div class="label">Q1 − Q5 spread</div><div class="value ${toneClass(s.mean_q1_q5_spread)}">${pct(s.mean_q1_q5_spread, 2)}</div><div class="sub">Per 20-session period, vs sector</div></div>
        <div class="kpi"><div class="label">Quintile ordering</div><div class="value">${monotone ? 'Monotone' : 'Not monotone'}</div><div class="sub">On average across folds</div></div>
      </div>
      ${raw(panel({ title: 'Rank IC by rebalance', note: 'Spearman correlation between the score and the realised sector-relative return in each month. The line is the 12-month rolling mean.', body: '<div id="ic"></div>' }))}
      <div class="grid cols-2 section-gap">
        ${raw(panel({ title: 'Average return by quintile', note: 'Mean realised 20-session return relative to sector. With predictive power, Q1 > Q2 > … > Q5.', body: '<div id="quintiles"></div>' }))}
        ${raw(panel({ title: 'Distribution of monthly IC', note: `Bins of 0.05.${outside ? ` ${outside} month(s) fall outside ±0.40.` : ''}`, body: '<div id="hist"></div>' }))}
      </div>
      <div class="section-gap" id="decay-row">${raw(panel({ title: 'Signal decay', note: 'Mean Rank IC of each month\'s scores against sector-relative returns over different horizons. Models are trained for 20 sessions; a fast fall-off means a short-lived signal.', body: '<div id="decay-legend"></div><div id="decay"></div>' }))}</div>
      <div class="grid cols-2 section-gap" id="sector-row">
        ${raw(panel({ title: 'Ranking skill by sector', note: 'Mean Rank IC among stocks in the same sector. Sectors with few names are noisy.', body: '<div id="sector-bars"></div>' }))}
        ${raw(panel({ title: 'Sector detail', note: 'Active weight: the top-ranked sleeve\'s sector share minus the universe\'s, averaged over folds.', body: '<div id="sector-table"></div>', flush: true }))}
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
    const decay = index.ws.decay || [];
    if (!decay.length) {
      document.getElementById('decay-row').hidden = true;
    } else {
      const horizons = [...new Set(decay.map((row) => row.horizon))].sort((a, b) => a - b);
      const decaySeries = index.models.map((id) => ({
        label: index.labels[id], color: modelColor(id), width: id === model ? 2.8 : 1.4,
        values: horizons.map((h) => decay.find((row) => row.model === id && row.horizon === h)?.mean_rank_ic ?? NaN),
      }));
      document.getElementById('decay-legend').innerHTML = legend(decaySeries);
      lineChart(document.getElementById('decay'), {
        dates: horizons.map((h) => `${h} sessions`), xFormat: (value) => value, series: decaySeries, height: 240, baseline: 0,
        yFormat: (value) => value.toFixed(3), label: 'Mean Rank IC by forward horizon for each model',
      });
    }

    const sectors = (index.ws.sectors || []).filter((row) => row.model === model);
    if (!sectors.length) {
      document.getElementById('sector-row').hidden = true;
    } else {
      document.getElementById('sector-bars').innerHTML = hbars(
        [...sectors].sort((a, b) => b.mean_rank_ic - a.mean_rank_ic)
          .map((row) => ({ label: `${sectorShort(row.sector)} (${row.names})`, value: row.mean_rank_ic ?? 0 })),
        { signed: true, format: (value) => num(value, 3, { sign: true }), color, negativeColor: 'var(--neg)' },
      );
      dataTable(document.getElementById('sector-table'), {
        rows: sectors, sortKey: 'mean_active_weight',
        columns: [
          { key: 'sector', label: 'Sector', render: (row) => html`${sectorShort(row.sector)} <span class="muted">(${row.names})</span>` },
          { key: 'mean_rank_ic', label: 'Mean IC', num: true, render: (row) => html`<span class="${toneClass(row.mean_rank_ic)}">${num(row.mean_rank_ic, 3)}</span>` },
          { key: 'positive_ic_rate', label: 'IC > 0', num: true, render: (row) => pct(row.positive_ic_rate, 0) },
          { key: 'mean_active_weight', label: 'Active weight', num: true, render: (row) => pct(row.mean_active_weight, 1, { sign: true }) },
        ],
      });
    }

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
