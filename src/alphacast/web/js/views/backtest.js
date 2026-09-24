import { categoryBars, columnChart, legend, lineChart } from '../charts.js';
import { BENCH_COLOR, modelColor } from '../data.js';
import { cadence, cumulative, date, downloadFile, drawdowns, html, mean, num, pct, raw, rolling, std, toCsv, toneClass } from '../format.js';
import { term } from '../glossary.js';
import { dataTable } from '../table.js';
import { panel } from './parts.js';

const sharpe = (returns) => { const sd = std(returns); return sd > 0 ? (Math.sqrt(12) * mean(returns)) / sd : 0; };
const annualized = (returns) => returns.reduce((wealth, value) => wealth * (1 + value), 1) ** (12 / returns.length) - 1;

/** Net returns at any one-way cost, rebuilt from gross returns and turnover. */
function atCost(periods, bps) {
  return periods.map((row) => row.gross_return - (row.turnover * bps) / 10_000);
}

let chosenCost = null;

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
        <div class="kpi"><div class="label">${raw(term('sharpe', 'Sharpe, gross → net'))}</div><div class="value">${num(s.gross_sharpe, 2)} → ${num(s.net_sharpe, 2)}</div><div class="sub">Benchmark ${num(s.benchmark_sharpe, 2)}</div></div>
        <div class="kpi"><div class="label">${raw(term('info_ratio'))}</div><div class="value">${num(s.information_ratio, 2)}</div><div class="sub">Beat the universe in ${pct(s.hit_rate, 0)} of months</div></div>
        <div class="kpi"><div class="label">${raw(term('beta'))} · ${raw(term('alpha'))}</div><div class="value">${num(s.beta, 2)}</div><div class="sub">Alpha ${pct(s.alpha_annualized, 1, { sign: true })}/yr · t ${num(s.alpha_t_stat, 1)}</div></div>
        <div class="kpi"><div class="label">${raw(term('drawdown'))}</div><div class="value neg">${pct(s.max_drawdown)}</div><div class="sub">Benchmark ${pct(s.benchmark_max_drawdown)}</div></div>
        <div class="kpi"><div class="label">${raw(term('turnover', 'Avg monthly turnover'))}</div><div class="value">${pct(s.mean_turnover, 0)}</div><div class="sub">Cost drag ${pct(s.annualized_cost_drag, 2)} per year</div></div>
        <div class="kpi"><div class="label">Terminal growth, net</div><div class="value ${toneClass(s.net_terminal_growth - s.benchmark_terminal_growth)}">${pct(s.net_terminal_growth, 0)}</div><div class="sub">Gross ${pct(s.gross_terminal_growth, 0)} · benchmark ${pct(s.benchmark_terminal_growth, 0)}</div></div>
      </div>
      ${raw(panel({ title: 'Growth of $1', note: `${periods.length} monthly out-of-sample holding periods from ${date(dates[0])} to ${date(periods.at(-1).date)}. The top ${index.ws.config.top_n} names are rebalanced ${cadence(index.ws.config.rebalance_every_folds)} and each period earns the next 20 sessions. The dashed grey line scales the universe to the sleeve's full-period beta, a risk-matched comparison measured after the fact.`, body: '<div id="growth-legend"></div><div id="growth"></div>' }))}
      <div class="grid cols-2 section-gap">
        ${raw(panel({ title: 'Drawdown', note: 'Net value against its running peak.', body: '<div id="dd-legend"></div><div id="drawdown"></div>' }))}
        ${raw(panel({ title: 'Rolling 12-month active return', note: 'Compounded net return minus the equal-weight universe.', body: '<div id="active"></div>' }))}
      </div>
      <div class="section-gap">${raw(panel({ title: 'Cost sensitivity', note: 'Net results rebuilt from gross returns and turnover at any one-way trading cost. The benchmark is untraded.', actions: '<label class="field compact"><span>Cost</span><input id="cost-slider" type="range" min="0" max="100" step="1" aria-label="One-way cost in basis points"><output id="cost-value" class="mono" style="min-width:56px;text-align:right"></output></label>', body: '<div class="grid cols-main"><div><div id="cost-legend"></div><div id="cost-chart"></div></div><div id="cost-readout"></div></div>' }))}</div>
      <div class="section-gap">${raw(panel({ title: 'Rolling 24-month beta', note: 'Regression of the sleeve\'s monthly net returns on the universe over the trailing two years. Above 1 means the sleeve amplified market moves in that window.', body: '<div id="beta-legend"></div><div id="beta"></div>' }))}</div>
      <div class="section-gap">${raw(panel({ title: 'Calendar-year returns', note: 'Monthly net returns compounded within each calendar year. Partial first and last years are marked.', body: '<div id="years-chart"></div><div class="table-wrap section-gap" id="years"></div>' }))}</div>
      <div class="grid cols-2 section-gap">
        ${raw(panel({ title: 'Turnover by rebalance', note: 'One-way share of the book traded. The first period is the starting allocation.', body: '<div id="turnover"></div>' }))}
        ${raw(panel({ title: 'Period returns', note: 'Most recent first.', actions: '<button class="button small" id="csv" type="button">Export CSV</button>', body: '<div class="scroll-table" style="max-height:300px" id="periods"></div>', flush: true }))}
      </div>`;

    const growthSeries = [
      { label: 'Net of costs', color, values: net },
      { label: 'Gross', color, values: gross, dash: true, width: 1.5 },
      { label: 'Equal-weight universe', color: BENCH_COLOR, values: bench },
      ...(Number.isFinite(s.beta) ? [{
        label: `Universe at the sleeve's beta (${num(s.beta, 2)}×)`, color: BENCH_COLOR, dash: true, width: 1.5,
        values: [1, ...cumulative(periods.map((row) => s.beta * row.benchmark_return))],
      }] : []),
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
    const benchReturns = periods.map((row) => row.benchmark_return);
    const benchSharpe = sharpe(benchReturns);
    const meanTurnover = mean(periods.map((row) => row.turnover));
    const grossEdge = mean(periods.map((row) => row.gross_return - row.benchmark_return));
    const breakEven = meanTurnover > 0 ? (grossEdge / meanTurnover) * 10_000 : Infinity;
    // Cost at which the risk-adjusted edge is gone, searched in 1 bp steps.
    let sharpeEven = null;
    for (let bps = 0; bps <= 1000; bps += 1) {
      if (sharpe(atCost(periods, bps)) <= benchSharpe) { sharpeEven = bps; break; }
    }
    const grid = Array.from({ length: 21 }, (_, i) => i * 5);
    const costSeries = [
      { label: 'Net Sharpe', color, values: grid.map((bps) => sharpe(atCost(periods, bps))) },
      { label: 'Universe Sharpe', color: BENCH_COLOR, values: grid.map(() => benchSharpe), dash: true },
    ];
    document.getElementById('cost-legend').innerHTML = legend(costSeries);
    lineChart(document.getElementById('cost-chart'), {
      dates: grid.map((bps) => `${bps} bps`), xFormat: (value) => value, series: costSeries, height: 220,
      yFormat: (value) => value.toFixed(2), label: 'Net Sharpe ratio across one-way trading costs from 0 to 100 basis points',
    });
    const slider = document.getElementById('cost-slider');
    const output = document.getElementById('cost-value');
    const readout = document.getElementById('cost-readout');
    const update = () => {
      const bps = Number(slider.value);
      chosenCost = bps;
      const net = atCost(periods, bps);
      const active = net.map((value, i) => value - benchReturns[i]);
      output.textContent = `${bps} bps`;
      readout.innerHTML = html`
        <div class="kpis" style="grid-template-columns:repeat(2,minmax(0,1fr));margin:0">
          <div class="kpi"><div class="label">Net Sharpe</div><div class="value ${toneClass(sharpe(net) - benchSharpe)}">${num(sharpe(net), 2)}</div><div class="sub">Universe ${num(benchSharpe, 2)}</div></div>
          <div class="kpi"><div class="label">Annualized, net</div><div class="value">${pct(annualized(net))}</div><div class="sub">Universe ${pct(annualized(benchReturns))}</div></div>
          <div class="kpi"><div class="label">Cost drag</div><div class="value">${pct((meanTurnover * bps * 12) / 10_000, 2)}</div><div class="sub">per year at ${pct(meanTurnover, 0)} turnover</div></div>
          <div class="kpi"><div class="label">Beat the universe</div><div class="value">${pct(active.filter((value) => value > 0).length / active.length, 0)}</div><div class="sub">of months</div></div>
        </div>
        <p class="note">${raw(sharpeEven === 0 ? 'Even before costs, the sleeve does not beat the universe on a risk-adjusted basis.'
          : `Net Sharpe falls to the universe's at about <b>${sharpeEven ?? '1,000+'} bps</b> one way${Number.isFinite(breakEven) && breakEven > 0 ? `; the raw return edge lasts to about <b>${Math.round(breakEven)} bps</b>, because the sleeve also carries more volatility` : ''}. The run was charged ${index.ws.config.transaction_cost_bps} bps.`)}</p>`;
    };
    slider.value = String(chosenCost ?? index.ws.config.transaction_cost_bps);
    slider.addEventListener('input', update);
    update();

    // Rolling OLS beta over the trailing 24 months.
    const window24 = 24;
    const rollingBeta = periods.map((_, i) => {
      if (i + 1 < window24) return NaN;
      const y = periods.slice(i + 1 - window24, i + 1).map((row) => row.net_return);
      const x = periods.slice(i + 1 - window24, i + 1).map((row) => row.benchmark_return);
      const mx = mean(x);
      const my = mean(y);
      const cov = x.reduce((sum, xi, j) => sum + (xi - mx) * (y[j] - my), 0);
      const varx = x.reduce((sum, xi) => sum + (xi - mx) ** 2, 0);
      return varx > 0 ? cov / varx : NaN;
    });
    const betaSeries = [
      { label: 'Rolling beta', color, values: rollingBeta },
      { label: 'Full-period beta', color: BENCH_COLOR, values: periods.map(() => s.beta), dash: true },
    ];
    document.getElementById('beta-legend').innerHTML = legend(betaSeries);
    lineChart(document.getElementById('beta'), {
      dates: periods.map((row) => row.date), series: betaSeries, height: 220, baseline: 1,
      yFormat: (value) => value.toFixed(1), tooltipFormat: (value) => value.toFixed(2),
      label: 'Rolling 24-month beta of the sleeve to the equal-weight universe',
    });

    const byYear = new Map();
    periods.forEach((row) => {
      const year = row.date.slice(0, 4);
      const entry = byYear.get(year) || { year, net: 1, bench: 1, months: 0 };
      entry.net *= 1 + row.net_return;
      entry.bench *= 1 + row.benchmark_return;
      entry.months += 1;
      byYear.set(year, entry);
    });
    const years = [...byYear.values()].map((entry) => ({
      year: entry.year, months: entry.months,
      net: entry.net - 1, bench: entry.bench - 1, active: entry.net - entry.bench,
    }));
    const beat = years.filter((row) => row.months >= 12 && row.active > 0).length;
    const full = years.filter((row) => row.months >= 12).length;
    categoryBars(document.getElementById('years-chart'), {
      labels: years.map((row) => (row.months < 12 ? `${row.year}*` : row.year)),
      values: years.map((row) => row.active), height: 200,
      colors: years.map((row) => (row.active >= 0 ? 'var(--pos)' : 'var(--neg)')),
      yFormat: (value) => pct(value, 0), label: 'Active return over the universe by calendar year',
      tooltipRows: (i) => [
        { label: 'Sleeve, net', value: pct(years[i].net, 1) },
        { label: 'Universe', value: pct(years[i].bench, 1) },
        { label: 'Active', value: pct(years[i].active, 1, { sign: true }) },
        { label: 'Months', value: String(years[i].months) },
      ],
    });
    dataTable(document.getElementById('years'), {
      rows: years, sortKey: 'year', sortDir: 'desc',
      columns: [
        { key: 'year', label: 'Year', render: (row) => (row.months < 12 ? html`${row.year} <span class="muted">(${row.months} mo)</span>` : row.year) },
        { key: 'net', label: 'Sleeve, net', num: true, render: (row) => html`<span class="${toneClass(row.net)}">${pct(row.net, 1)}</span>` },
        { key: 'bench', label: 'Universe', num: true, render: (row) => pct(row.bench, 1) },
        { key: 'active', label: 'Active', num: true, render: (row) => html`<span class="${toneClass(row.active)}">${pct(row.active, 1, { sign: true })}</span>` },
      ],
    });
    document.querySelector('#years').insertAdjacentHTML('afterend', `<p class="note">Beat the universe in ${beat} of ${full} full years.</p>`);

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
