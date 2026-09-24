// A one-page research memo for the active run and model, laid out to print or save as PDF.

import { legend, lineChart } from '../charts.js';
import { BENCH_COLOR, liveRows, modelColor } from '../data.js';
import { cadence, cumulative, date, html, int, num, pct, raw, sectorShort } from '../format.js';
import { verdict } from './overview.js';
import { statusBadge } from './parts.js';

const HEALTH_WORDS = { healthy: 'Healthy', watch: 'Watch', degraded: 'Degraded' };

function portfolioRule(config) {
  return [
    `equal-weight top ${config.top_n}, long-only`,
    `rebalanced ${cadence(config.rebalance_every_folds)}`,
    config.max_per_sector ? `at most ${config.max_per_sector} per sector` : null,
    config.hold_buffer ? `holdings kept while in the top ${config.hold_buffer}` : null,
    config.neutralize_volatility ? 'scores neutralised to volatility' : null,
    `${config.transaction_cost_bps} bps one-way costs`,
  ].filter(Boolean).join(', ');
}

export default {
  title: 'Report',
  subtitle: (ctx) => `One-page research memo for ${ctx.index.labels[ctx.model]}. Print it or save it as PDF.`,
  render(ctx) {
    const { index, model } = ctx;
    const { ws } = index;
    const summary = index.summaries[model];
    const health = index.monitoring[model];
    const holdings = liveRows(index, model).filter((row) => row.in_portfolio);
    const run = ctx.runs.find((item) => item.id === ctx.runId);
    const board = [...index.models].sort((a, b) => index.summaries[b].mean_rank_ic - index.summaries[a].mean_rank_ic);
    const periods = index.periods[model];

    ctx.el.innerHTML = html`
      <div class="report-actions no-print">
        <p class="muted">Generated from the workspace in view. Switch the model in the toolbar to write the memo for another one.</p>
        <button type="button" class="button primary" id="print-report">Print or save as PDF</button>
      </div>
      <article class="report" aria-labelledby="report-title">
        <header class="report-head">
          <div>
            <p class="report-kicker">AlphaCast · research memo</p>
            <h2 id="report-title">${index.labels[model]} on ${ws.dataset}</h2>
            <p class="muted">${run?.name || 'Workspace'} · signal as of ${date(ws.signal_date)} · ${int(summary.folds)} monthly out-of-sample folds, ${date(periods[0].date)} to ${date(ws.last_rebalance)}</p>
          </div>
          <div class="report-status"><span>Model health</span>${raw(statusBadge(health.status))}</div>
        </header>

        <section class="report-section">
          <h3>Bottom line</h3>
          <dl class="verdict-points">${verdict(index, model).map(([label, text]) => raw(html`<div><dt>${label}</dt><dd>${text}</dd></div>`))}</dl>
        </section>

        <section class="report-section report-figures">
          <div class="report-kpi"><span>Mean Rank IC</span><b>${num(summary.mean_rank_ic, 3)}</b><small>t = ${num(summary.ic_t_stat, 2)} · Holm p = ${num(summary.p_value_holm, 2)}</small></div>
          <div class="report-kpi"><span>Net Sharpe</span><b>${num(summary.net_sharpe, 2)}</b><small>Universe ${num(summary.benchmark_sharpe, 2)}</small></div>
          <div class="report-kpi"><span>Annualised, net</span><b>${pct(summary.annualized_net_return)}</b><small>Universe ${pct(summary.annualized_benchmark_return)}</small></div>
          <div class="report-kpi"><span>Beta · alpha a year</span><b>${num(summary.beta, 2)} · ${pct(summary.alpha_annualized, 1)}</b><small>Alpha t = ${num(summary.alpha_t_stat, 1)}</small></div>
          <div class="report-kpi"><span>Max drawdown</span><b>${pct(summary.max_drawdown)}</b><small>Universe ${pct(summary.benchmark_max_drawdown)}</small></div>
          <div class="report-kpi"><span>Turnover a month</span><b>${pct(summary.mean_turnover, 0)}</b><small>Cost drag ${pct(summary.annualized_cost_drag, 2)} a year</small></div>
        </section>

        <section class="report-section">
          <h3>Growth of $1, net of costs</h3>
          <div id="report-legend"></div><div id="report-growth"></div>
        </section>

        <section class="report-section">
          <h3>Every model on the same folds</h3>
          <div class="table-wrap"><table class="report-table">
            <thead><tr><th scope="col">Model</th><th class="num" scope="col">Mean IC</th><th class="num" scope="col">t</th><th class="num" scope="col">Holm p</th><th class="num" scope="col">Net Sharpe</th><th class="num" scope="col">Turnover</th><th class="num" scope="col">Beta</th><th class="num" scope="col">Alpha/yr</th><th scope="col">Health</th></tr></thead>
            <tbody>${board.map((id) => {
              const row = index.summaries[id];
              return raw(html`<tr class="${id === model ? 'selected' : ''}"><th scope="row"><span class="dot" style="background:${raw(modelColor(id))}"></span>${index.labels[id]}</th><td class="num">${num(row.mean_rank_ic, 3)}</td><td class="num">${num(row.ic_t_stat, 2)}</td><td class="num">${num(row.p_value_holm, 2)}</td><td class="num">${num(row.net_sharpe, 2)}</td><td class="num">${pct(row.mean_turnover, 0)}</td><td class="num">${num(row.beta, 2)}</td><td class="num">${pct(row.alpha_annualized, 1)}</td><td>${HEALTH_WORDS[index.monitoring[id].status]}</td></tr>`);
            })}
            <tr class="report-bench"><th scope="row">Equal-weight universe</th><td></td><td></td><td></td><td class="num">${num(summary.benchmark_sharpe, 2)}</td><td></td><td class="num">1.00</td><td></td><td></td></tr></tbody>
          </table></div>
        </section>

        <section class="report-section">
          <h3>Current book · ${holdings.length} names</h3>
          <ol class="report-book">${holdings.map((row) => raw(html`<li><b>${row.ticker}</b><span>${sectorShort(row.sector)}</span>${row.was_held ? '' : raw('<em>new</em>')}</li>`))}</ol>
        </section>

        <section class="report-section report-two">
          <div>
            <h3>Setup</h3>
            <ul class="report-list">
              <li>${int(ws.quality.accepted_tickers)} securities, ${date(ws.quality.first_date)} to ${date(ws.quality.last_date)}; ${int(ws.quality.dropped_sessions)} partial session${ws.quality.dropped_sessions === 1 ? '' : 's'} dropped.</li>
              <li>Target: next ${ws.config.horizon_sessions}-session return relative to the stock's sector.</li>
              <li>Walk-forward monthly folds; training ends ${ws.config.embargo_sessions} sessions before each test date.</li>
              <li>Portfolio: ${portfolioRule(ws.config)}.</li>
              <li>Health: last ${ws.config.monitoring_window} folds tested against the earlier record, in standard errors.</li>
            </ul>
          </div>
          <div>
            <h3>Limits</h3>
            <ul class="report-list">${ws.limits.map((item) => raw(html`<li>${item}</li>`))}</ul>
          </div>
        </section>
        <footer class="report-foot muted">Generated ${date(new Date().toISOString().slice(0, 10))} from alphacast.onrender.com. Historical research, not investment advice.</footer>
      </article>`;

    document.getElementById('print-report').addEventListener('click', () => window.print());
    const dates = [periods[0].train_end, ...periods.map((row) => row.date)];
    const series = [
      { label: `${index.labels[model]} (net)`, color: modelColor(model), values: [1, ...cumulative(periods.map((row) => row.net_return))] },
      { label: 'Equal-weight universe', color: BENCH_COLOR, values: [1, ...cumulative(periods.map((row) => row.benchmark_return))], dash: true },
    ];
    document.getElementById('report-legend').innerHTML = legend(series);
    lineChart(document.getElementById('report-growth'), {
      dates, series, height: 220, baseline: 1, yFormat: (value) => `$${value.toFixed(1)}`, tooltipFormat: (value) => `$${value.toFixed(2)}`,
      label: 'Growth of one dollar for the top-ranked sleeve against the equal-weight universe',
    });
  },
};
