import { hbars, pairedBars } from '../charts.js';
import { liveRows } from '../data.js';
import { cadence, html, mean, num, pct, raw, sectorShort, toneClass } from '../format.js';

const median = (values) => {
  const sorted = values.filter(Number.isFinite).sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
};
import { dataTable } from '../table.js';
import { panel, pctBar, rankChange, tickerLink } from './parts.js';

export default {
  title: 'Portfolio',
  subtitle: (ctx) => `Equal-weight top ${ctx.index.ws.config.top_n} by ${ctx.index.labels[ctx.model]}${ctx.index.ws.config.max_per_sector ? `, at most ${ctx.index.ws.config.max_per_sector} per sector` : ''}, long-only, rebalanced ${cadence(ctx.index.ws.config.rebalance_every_folds)}${ctx.index.ws.config.hold_buffer ? `, holdings kept while in the top ${ctx.index.ws.config.hold_buffer}` : ''}`,
  render(ctx) {
    const { index, model } = ctx;
    const rows = liveRows(index, model);
    const holdings = rows.filter((row) => row.in_portfolio);
    const entering = holdings.filter((row) => !row.was_held);
    const exiting = rows.filter((row) => row.was_held && !row.in_portfolio);
    const previousCount = rows.filter((row) => row.was_held).length || holdings.length;
    // One-way turnover between two equal-weight books of possibly different sizes.
    const turnover = previousCount
      ? rows.reduce((sum, row) => sum + Math.abs((row.in_portfolio ? 1 / holdings.length : 0) - (row.was_held ? 1 / previousCount : 0)), 0) / 2
      : 0;
    const cost = turnover * index.ws.config.transaction_cost_bps / 10_000;

    const sectors = index.sectors.map((sector) => {
      const universe = rows.filter((row) => row.sector === sector).length / rows.length;
      const held = holdings.filter((row) => row.sector === sector).length / holdings.length;
      return { sector, universe, held, active: held - universe };
    }).sort((a, b) => b.held - a.held || b.universe - a.universe);
    const summary = index.summaries[model];

    ctx.el.innerHTML = html`
      <div class="kpis">
        <div class="kpi"><div class="label">Holdings</div><div class="value">${holdings.length}</div><div class="sub">${new Set(holdings.map((row) => row.sector)).size} sectors represented</div></div>
        <div class="kpi"><div class="label">Changes at this signal</div><div class="value">+${entering.length} / −${exiting.length}</div><div class="sub">Entering / exiting vs last rebalance</div></div>
        <div class="kpi"><div class="label">Implied turnover</div><div class="value">${pct(turnover, 0)}</div><div class="sub">Cost ≈ ${pct(cost, 2)} at ${index.ws.config.transaction_cost_bps} bps · history avg ${pct(summary.mean_turnover, 0)}</div></div>
        <div class="kpi"><div class="label">Largest sector</div><div class="value">${pct(sectors[0].held, 0)}</div><div class="sub">${sectorShort(sectors[0].sector)} · universe ${pct(sectors[0].universe, 0)}</div></div>
      </div>
      <div class="grid cols-main">
        ${raw(panel({ title: 'Target holdings', note: 'Weights if the book were rebalanced at the latest close.', body: '<div id="holdings"></div>', flush: true }))}
        <div class="stack">
          ${raw(panel({ title: 'Sector allocation', note: 'Portfolio weight against the equal-weight universe.', body: `
            ${pairedBars(sectors.map((row) => ({
              label: sectorShort(row.sector), a: row.held, b: row.universe, value: row.active, tone: toneClass(row.active),
              title: `${row.sector}: portfolio ${pct(row.held, 1)}, universe ${pct(row.universe, 1)}`,
            })), { labelA: 'Portfolio', labelB: 'Universe', format: (value) => pct(value, 0, { sign: true }) })}
            <p class="note">Right column: active weight vs universe. ${index.ws.config.max_per_sector ? `This run caps the sleeve at ${index.ws.config.max_per_sector} names per sector.` : 'The sleeve has no sector constraint, so concentration is a result of the ranking and worth watching. New runs can cap names per sector.'}</p>` }))}
          ${raw(panel({ title: 'Factor tilts', note: 'Average percentile of the holdings minus the universe average of 50. Positive means the book leans that way.', body: '<div id="tilts"></div><div class="table-wrap section-gap" id="tilt-table"></div>' }))}
          ${raw(panel({ title: 'Entering', note: 'New to the book at this signal.', body: '<div id="entering"></div>', flush: true }))}
          ${raw(panel({ title: 'Exiting', note: 'Held at the last rebalance, now outside the top ranks.', body: '<div id="exiting"></div>', flush: true }))}
        </div>
      </div>`;

    const factors = [['momentum', 'Momentum'], ['relative_strength', 'Relative strength'], ['low_risk', 'Low risk'], ['liquidity', 'Liquidity']];
    document.getElementById('tilts').innerHTML = hbars(
      factors.map(([key, label]) => ({ label, value: mean(holdings.map((row) => row[key])) - 50 })),
      { signed: true, format: (value) => num(value, 0, { sign: true }), color: 'var(--series-1)', negativeColor: 'var(--series-2)' },
    );
    const raws = [['momentum_12_1', '12-1 momentum'], ['return_63', '3M return'], ['volatility_60', '60D volatility'], ['drawdown_252', '12M drawdown']];
    dataTable(document.getElementById('tilt-table'), {
      rows: raws.map(([key, label]) => ({ label, held: median(holdings.map((row) => row[key])), universe: median(rows.map((row) => row[key])) })),
      columns: [
        { key: 'label', label: 'Median', sortable: false },
        { key: 'held', label: 'Holdings', num: true, sortable: false, render: (row) => pct(row.held, 1) },
        { key: 'universe', label: 'Universe', num: true, sortable: false, render: (row) => pct(row.universe, 1) },
      ],
    });

    const open = (row) => ctx.navigate(`#/security/${row.ticker}`);
    dataTable(document.getElementById('holdings'), {
      rows: holdings, sortKey: 'rank', sortDir: 'asc', onRowClick: open,
      columns: [
        { key: 'rank', label: 'Rank', num: true },
        { key: 'ticker', label: 'Ticker', render: (row) => tickerLink(row.ticker) },
        { key: 'sector', label: 'Sector', render: (row) => html`<span class="sector">${sectorShort(row.sector)}</span>` },
        { key: 'weight', label: 'Weight', num: true, render: (row) => pct(row.weight, 1) },
        { key: 'percentile', label: 'Score pct.', num: true, render: (row) => pctBar(row.percentile) },
        { key: 'rank_change', label: 'Δ Rank', num: true, render: (row) => rankChange(row.rank_change) },
        { key: 'was_held', label: 'Status', sort: (row) => (row.was_held ? 1 : 0), render: (row) => (row.was_held ? '<span class="tag">Held</span>' : '<span class="tag new">Entering</span>') },
      ],
    });
    const small = [
      { key: 'ticker', label: 'Ticker', render: (row) => tickerLink(row.ticker) },
      { key: 'rank', label: 'Rank now', num: true },
      { key: 'previous_rank', label: 'Rank before', num: true, render: (row) => row.previous_rank ?? '—' },
    ];
    dataTable(document.getElementById('entering'), { rows: entering, columns: small, sortKey: 'rank', sortDir: 'asc', onRowClick: open, empty: 'No new names.' });
    dataTable(document.getElementById('exiting'), { rows: exiting, columns: small, sortKey: 'rank', sortDir: 'asc', onRowClick: open, empty: 'No exits.' });
  },
};
