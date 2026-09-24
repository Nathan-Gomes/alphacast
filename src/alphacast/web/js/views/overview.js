import { legend, lineChart } from '../charts.js';
import { BENCH_COLOR, leadingModel, liveRows, modelColor, votingModels } from '../data.js';
import { cumulative, date, html, num, pct, raw, sectorShort, toneClass } from '../format.js';
import { term } from '../glossary.js';
import { dataTable } from '../table.js';
import { consensusCell, pctBar, rankChange, statusBadge, tickerLink } from './parts.js';
import { bindStars, starButton, watchlist } from '../watchlist.js';

/** The research read-out as short labelled points: [label, text]. */
export function verdict(index, model) {
  const leader = leadingModel(index);
  const best = index.summaries[leader];
  const baseline = index.summaries.momentum;
  const health = index.monitoring[model];
  const ensemble = index.summaries.ensemble;
  const points = [];
  points.push(['Signal', `${index.labels[leader]} ranks best: mean Rank IC ${num(best.mean_rank_ic, 3)}, positive in ${pct(best.positive_ic_rate, 0)} of ${best.folds} months.`]);
  if (Number.isFinite(best.p_value_holm) && index.models.length > 1) {
    points.push(['Evidence', best.p_value_holm < 0.05
      ? `Significant after adjusting for ${index.models.length} models (t = ${num(best.ic_t_stat, 1)}, Holm p = ${num(best.p_value_holm, 3)}).`
      : `Suggestive, not conclusive: t = ${num(best.ic_t_stat, 1)}, but Holm p = ${num(best.p_value_holm, 2)} across ${index.models.length} models.${ensemble && leader !== 'ensemble' ? ` The ensemble fixed in advance reaches IC ${num(ensemble.mean_rank_ic, 3)}.` : ''}`]);
  }
  if (baseline && leader !== 'momentum') {
    points.push(['After costs', `Net Sharpe ${num(best.net_sharpe, 2)} against ${num(baseline.net_sharpe, 2)} for momentum and ${num(best.benchmark_sharpe, 2)} for the universe, at ${pct(best.mean_turnover, 0)} monthly turnover.`]);
  }
  const books = (index.ws.book_sizes || []).filter((row) => row.model === leader).sort((a, b) => a.top_n - b.top_n);
  if (books.length > 2) {
    const sharpes = books.map((row) => row.net_sharpe);
    const low = Math.min(...sharpes);
    const concentrated = books[0].annualized_active_return > books.at(-1).annualized_active_return;
    points.push(['Robustness', `Net Sharpe ${num(low, 2)} to ${num(Math.max(...sharpes), 2)} from ${books[0].top_n} to ${books.at(-1).top_n} names${low > best.benchmark_sharpe ? ', above the universe at every size' : ''}; ${concentrated ? 'active return rises as the book concentrates, as it should if the ranking is informative.' : 'active return does not rise as the book concentrates, so the top of the ranking is not where the edge is.'}`]);
  }
  if (Number.isFinite(best.beta)) {
    points.push(['Exposure', `Beta ${num(best.beta, 2)} to the universe; alpha after that is ${pct(best.alpha_annualized, 1)} a year (t = ${num(best.alpha_t_stat, 1)}).`]);
  }
  if (health) {
    points.push(['Health', health.status === 'healthy'
      ? `${index.labels[model]} is in line with its history over the last ${health.window_folds} folds.`
      : `${index.labels[model]} is ${health.status === 'watch' ? 'on watch' : health.status}: recent Rank IC ${num(health.recent_mean_rank_ic, 3)} against ${num(health.historical_mean_rank_ic, 3)} earlier, ${num(Math.abs(health.change_z), 1)} standard errors ${health.change_z < 0 ? 'lower' : 'higher'}${health.status === 'degraded' ? '' : ', within the range noise can produce'}.`]);
  }
  return points;
}

export default {
  title: 'Overview',
  subtitle: (ctx) => `Current signal and research health for ${ctx.index.labels[ctx.model]}`,
  render(ctx) {
    const { index, model } = ctx;
    const summary = index.summaries[model];
    const health = index.monitoring[model];
    const rows = liveRows(index, model);
    const holdings = rows.filter((row) => row.in_portfolio);
    const entering = holdings.filter((row) => !row.was_held).length;

    ctx.el.innerHTML = html`
      <div class="kpis">
        <div class="kpi"><div class="label">Signal date</div><div class="value">${date(index.ws.signal_date)}</div><div class="sub">Last evaluated rebalance ${date(index.ws.last_rebalance)}</div></div>
        <div class="kpi"><div class="label">${raw(term('rank_ic', 'Mean Rank IC'))}</div><div class="value">${num(summary.mean_rank_ic, 3)}</div><div class="sub">t = ${num(summary.ic_t_stat, 2)} · ${pct(summary.positive_ic_rate, 0)} positive months</div></div>
        <div class="kpi"><div class="label">${raw(term('sharpe', 'Net Sharpe'))}</div><div class="value">${num(summary.net_sharpe, 2)}</div><div class="sub">Benchmark ${num(summary.benchmark_sharpe, 2)} · IR ${num(summary.information_ratio, 2)}</div></div>
        <div class="kpi"><div class="label">Annualized, net</div><div class="value ${toneClass(summary.annualized_net_return - summary.annualized_benchmark_return)}">${pct(summary.annualized_net_return)}</div><div class="sub">Benchmark ${pct(summary.annualized_benchmark_return)}</div></div>
        <div class="kpi"><div class="label">${raw(term('health'))}</div><div class="value">${raw(statusBadge(health.status))}</div><div class="sub">Recent IC ${num(health.recent_mean_rank_ic, 3)} over ${health.window_folds} folds</div></div>
        <div class="kpi"><div class="label">Portfolio</div><div class="value">${holdings.length} names</div><div class="sub">${entering} entering at this signal</div></div>
      </div>
      <section class="verdict" aria-labelledby="verdict-title"><h2 id="verdict-title">Research read-out</h2><dl class="verdict-points">${verdict(index, model).map(([label, text]) => raw(html`<div><dt>${label}</dt><dd>${text}</dd></div>`))}</dl></section>
      <div class="grid cols-main">
        <div class="stack">
          <section class="panel">
            <div class="panel-head"><div><h2>Highest ranked now</h2><p>Scores from the ${date(index.ws.signal_date)} close. Outcomes are unknown until the next 20 sessions pass.</p></div><div class="actions"><a class="button small" href="#/screener">Open screener</a></div></div>
            <div class="panel-body flush table-wrap" id="top-table"></div>
          </section>
          <section class="panel" id="watch-panel" hidden>
            <div class="panel-head"><div><h2>Watchlist</h2><p>Your starred tickers under the active model. Stored in this browser.</p></div><div class="actions"><a class="button small" href="#/screener">Manage</a></div></div>
            <div class="panel-body flush table-wrap" id="watch-table"></div>
          </section>
          <section class="panel">
            <div class="panel-head"><div><h2>Lowest ranked now</h2><p>The bottom quintile: names the model expects to lag their sector.</p></div></div>
            <div class="panel-body flush table-wrap" id="bottom-table"></div>
          </section>
        </div>
        <div class="stack">
          <section class="panel">
            <div class="panel-head"><div><h2>Top-ranked sleeve vs universe</h2><p>Growth of $1, net of costs, monthly walk-forward.</p></div></div>
            <div class="panel-body"><div id="legend"></div><div id="equity"></div></div>
          </section>
          <section class="panel">
            <div class="panel-head"><div><h2>Consensus picks</h2><p>Stocks most models place in their top quintile today.</p></div></div>
            <div class="panel-body flush table-wrap" id="consensus-table"></div>
          </section>
          <section class="panel">
            <div class="panel-head"><div><h2>Model leaderboard</h2><p>Select a row to make it the active model.</p></div></div>
            <div class="panel-body flush table-wrap" id="leaderboard"></div>
          </section>
        </div>
      </div>`;

    const rankColumns = [
      { key: 'rank', label: 'Rank', num: true },
      { key: 'ticker', label: 'Ticker', render: (row) => tickerLink(row.ticker) },
      { key: 'sector', label: 'Sector', render: (row) => html`<span class="sector">${sectorShort(row.sector)}</span>` },
      { key: 'percentile', label: 'Score pct.', num: true, render: (row) => pctBar(row.percentile) },
      { key: 'rank_change', label: 'Δ Rank', num: true, title: 'Rank change since the last evaluated rebalance', render: (row) => rankChange(row.rank_change) },
    ];
    const open = (row) => ctx.navigate(`#/security/${row.ticker}`);
    dataTable(document.getElementById('top-table'), { columns: rankColumns, rows: rows.slice(0, 10), onRowClick: open });
    dataTable(document.getElementById('bottom-table'), { columns: rankColumns, rows: rows.slice(-5).reverse(), onRowClick: open });
    const picks = rows.filter((row) => row.consensus >= Math.max(2, Math.ceil(votingModels(index).length / 2)))
      .sort((a, b) => b.consensus - a.consensus || a.rank - b.rank).slice(0, 8);
    dataTable(document.getElementById('consensus-table'), {
      rows: picks, onRowClick: open, empty: 'No stock is in the top quintile of most models today.',
      columns: [
        { key: 'ticker', label: 'Ticker', sortable: false, render: (row) => tickerLink(row.ticker) },
        { key: 'sector', label: 'Sector', sortable: false, render: (row) => html`<span class="sector">${sectorShort(row.sector)}</span>` },
        { key: 'consensus', label: 'Models', num: true, sortable: false, render: (row) => consensusCell(row.consensus, votingModels(index).length) },
        { key: 'rank', label: `Rank`, num: true, sortable: false },
      ],
    });

    const renderWatch = () => {
      const starred = new Set(watchlist.all());
      const watched = rows.filter((row) => starred.has(row.ticker));
      document.getElementById('watch-panel').hidden = !watched.length;
      if (!watched.length) return;
      dataTable(document.getElementById('watch-table'), {
        columns: [{ key: 'star', label: '', srLabel: 'Watchlist', sortable: false, render: (row) => starButton(row.ticker) }, ...rankColumns],
        rows: watched, sortKey: 'rank', sortDir: 'asc', onRowClick: open,
        afterRender: (element) => bindStars(element, renderWatch),
      });
    };
    renderWatch();

    const periods = index.periods[model];
    const dates = [periods[0].train_end, ...periods.map((row) => row.date)];
    const series = [
      { label: `${index.labels[model]} (net)`, color: modelColor(model), values: [1, ...cumulative(periods.map((row) => row.net_return))] },
      { label: 'Equal-weight universe', color: BENCH_COLOR, values: [1, ...cumulative(periods.map((row) => row.benchmark_return))], dash: true },
    ];
    document.getElementById('legend').innerHTML = legend(series);
    lineChart(document.getElementById('equity'), {
      dates, series, height: 230, baseline: 1, yFormat: (value) => `$${value.toFixed(1)}`, tooltipFormat: (value) => `$${value.toFixed(2)}`,
      label: 'Growth of one dollar for the top-ranked sleeve against the equal-weight universe',
    });

    const board = index.models.map((id) => ({ ...index.summaries[id], status: index.monitoring[id].status, label: index.labels[id] }));
    dataTable(document.getElementById('leaderboard'), {
      rows: board,
      sortKey: 'mean_rank_ic',
      rowClass: (row) => (row.model === model ? 'selected' : ''),
      onRowClick: (row) => ctx.setModel(row.model),
      columns: [
        { key: 'label', label: 'Model', render: (row) => html`<span class="dot" style="background:${raw(modelColor(row.model))}"></span>${row.label}` },
        { key: 'mean_rank_ic', label: 'IC', num: true, render: (row) => num(row.mean_rank_ic, 3) },
        { key: 'ic_t_stat', label: 't', num: true, render: (row) => num(row.ic_t_stat, 1) },
        { key: 'net_sharpe', label: 'Net SR', num: true, render: (row) => num(row.net_sharpe, 2) },
        { key: 'status', label: 'Health', render: (row) => statusBadge(row.status) },
      ],
    });
  },
};
