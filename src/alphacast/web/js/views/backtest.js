import { columnChart, legend, lineChart } from '../charts.js';
import { BENCH_COLOR, modelColor } from '../data.js';
import { cumulative, date, downloadFile, drawdowns, html, num, pct, raw, rolling, toCsv, toneClass } from '../format.js';
import { dataTable } from '../table.js';
import { panel } from './parts.js';

export default {
  title: 'Backtest',
  subtitle: (ctx) => `Walk-forward performance of the ${ctx.index.labels[ctx.model]} top-ranked sleeve`,
  render(ctx) {
    const { index, model } = ctx;
    const periods = index.periods[model];
    const s = index.summaries[model];
    const color = modelColor(model);
    const dates = [periods[0].train_end, ...periods.map((row) => row.date)];
    const net = [1, ...cumulative(periods.map((row) => row.net_return))];
    const gross = [1, ...cumulative(periods.map((row) => row.gross_return))];
    const bench = [1, ...cumulative(periods.map((row) => row.benchmark_return))];
    const active = periods.map((row) => row.net_return - row.benchmark_return);
    const rolling12 = rolling(active, 12, (values) => values.reduce((wealth, value) => wealth * (1 + value), 1) - 1);

    ctx.el.innerHTML = html`
      <div class="kpis">
        <div class="kpi"><div class="label">Annualized net return</div><div class="value">${pct(s.annualized_net_return)}</div><div class="sub">Benchmark ${pct(s.annualized_benchmark_return)}</div></div>
        <div class="kpi"><div class="label">Sharpe, gross → net</div><div class="value">${num(s.gross_sharpe, 2)} → ${num(s.net_sharpe, 2)}</div><div class="sub">Benchmark ${num(s.benchmark_sharpe, 2)}</div></div>
        <div class="kpi"><div class="label">Information ratio</div><div class="value">${num(s.information_ratio, 2)}</div><div class="sub">Beat the universe in ${pct(s.hit_rate, 0)} of months</div></div>
        <div class="kpi"><div class="label">Max drawdown</div><div class="value neg">${pct(s.max_drawdown)}</div><div class="sub">Benchmark ${pct(s.benchmark_max_drawdown)}</div></div>
        <div class="kpi"><div class="label">Avg monthly turnover</div><div class="value">${pct(s.mean_turnover, 0)}</div><div class="sub">Cost drag ${pct(s.annualized_cost_drag, 2)} per year</div></div>
        <div class="kpi"><div class="label">Terminal growth, net</div><div class="value ${toneClass(s.net_terminal_growth - s.benchmark_terminal_growth)}">${pct(s.net_terminal_growth, 0)}</div><div class="sub">Gross ${pct(s.gross_terminal_growth, 0)} · benchmark ${pct(s.benchmark_terminal_growth, 0)}</div></div>
      </div>
      ${raw(panel({ title: 'Growth of $1', note: `${periods.length} monthly out-of-sample holding periods from ${date(dates[0])} to ${date(periods.at(-1).date)}. Each period holds the top ${index.ws.config.top_n} names for 20 sessions.`, body: '<div id="growth-legend"></div><div id="growth"></div>' }))}
      <div class="grid cols-2 section-gap">
        ${raw(panel({ title: 'Drawdown', note: 'Net value against its running peak.', body: '<div id="dd-legend"></div><div id="drawdown"></div>' }))}
        ${raw(panel({ title: 'Rolling 12-month active return', note: 'Compounded net return minus the equal-weight universe.', body: '<div id="active"></div>' }))}
      </div>
      <div class="grid cols-2 section-gap">
        ${raw(panel({ title: 'Turnover by rebalance', note: 'One-way share of the book traded. The first period is the starting allocation.', body: '<div id="turnover"></div>' }))}
        ${raw(panel({ title: 'Period returns', note: 'Most recent first.', actions: '<button class="button small" id="csv" type="button">Export CSV</button>', body: '<div class="scroll-table" style="max-height:300px" id="periods"></div>', flush: true }))}
      </div>`;

    const growthSeries = [
      { label: 'Net of costs', color, values: net },
      { label: 'Gross', color, values: gross, dash: true, width: 1.5 },
      { label: 'Equal-weight universe', color: BENCH_COLOR, values: bench },
    ];
    document.getElementById('growth-legend').innerHTML = legend(growthSeries);
    lineChart(document.getElementById('growth'), {
      dates, series: growthSeries, height: 300, baseline: 1,
      yFormat: (value) => `$${value.toFixed(1)}`, tooltipFormat: (value) => `$${value.toFixed(3)}`,
      label: 'Growth of one dollar: net, gross, and benchmark',
    });
    const ddSeries = [
      { label: 'Strategy', color, values: drawdowns(net), area: true },
      { label: 'Universe', color: BENCH_COLOR, values: drawdowns(bench), dash: true },
    ];
    document.getElementById('dd-legend').innerHTML = legend(ddSeries);
    lineChart(document.getElementById('drawdown'), {
      dates, series: ddSeries, height: 220, baseline: 0, yFormat: (value) => pct(value, 0), tooltipFormat: (value) => pct(value, 1),
      label: 'Drawdown of the strategy and the universe',
    });
    columnChart(document.getElementById('active'), {
      dates: periods.map((row) => row.date), values: rolling12, height: 220,
      yFormat: (value) => pct(value, 0), positive: 'var(--pos)', negative: 'var(--neg)',
      label: 'Rolling twelve-month active return',
      tooltipRows: (i) => [{ label: '12M active', value: pct(rolling12[i], 1, { sign: true }) }, { label: 'This month', value: pct(active[i], 2, { sign: true }) }],
    });
    columnChart(document.getElementById('turnover'), {
      dates: periods.map((row) => row.date), values: periods.map((row) => row.turnover), height: 220,
      yFormat: (value) => pct(value, 0), positive: color, label: 'Turnover by rebalance',
      tooltipRows: (i) => [{ label: 'Turnover', value: pct(periods[i].turnover, 0) }, { label: 'Cost', value: pct(periods[i].transaction_cost, 3) }],
    });
    const recent = [...periods].reverse().map((row) => ({ ...row, active: row.net_return - row.benchmark_return }));
    const columns = [
      { key: 'date', label: 'Rebalance', render: (row) => date(row.date) },
      { key: 'net_return', label: 'Net', num: true, render: (row) => html`<span class="${toneClass(row.net_return)}">${pct(row.net_return, 2)}</span>` },
      { key: 'benchmark_return', label: 'Universe', num: true, render: (row) => pct(row.benchmark_return, 2) },
      { key: 'active', label: 'Active', num: true, render: (row) => html`<span class="${toneClass(row.active)}">${pct(row.active, 2, { sign: true })}</span>` },
      { key: 'turnover', label: 'Turnover', num: true, render: (row) => pct(row.turnover, 0) },
      { key: 'regime', label: 'Regime', render: (row) => html`<span class="muted">${row.regime}</span>` },
    ];
    const table = dataTable(document.getElementById('periods'), { rows: recent, columns });
    document.getElementById('csv').addEventListener('click', () => downloadFile(`alphacast-${model}-backtest.csv`, toCsv(table.rows(), [
      { key: 'date', label: 'date' }, { key: 'gross_return', label: 'gross_return' }, { key: 'net_return', label: 'net_return' },
      { key: 'benchmark_return', label: 'benchmark_return' }, { key: 'turnover', label: 'turnover' },
      { key: 'transaction_cost', label: 'transaction_cost' }, { key: 'rank_ic', label: 'rank_ic' }, { key: 'regime', label: 'regime' },
    ])));
  },
};
