import { liveRows } from '../data.js';
import { html, num, pct, raw, sectorShort, toneClass } from '../format.js';
import { dataTable } from '../table.js';
import { panel, pctBar, rankChange, tickerLink } from './parts.js';

export default {
  title: 'Portfolio',
  subtitle: (ctx) => `Equal-weight top ${ctx.index.ws.config.top_n} by ${ctx.index.labels[ctx.model]}, long-only, rebalanced monthly`,
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
    const maxWeight = Math.max(...sectors.map((row) => Math.max(row.held, row.universe)), 0.01);
    const avg = (key) => holdings.reduce((sum, row) => sum + (row[key] ?? 0), 0) / holdings.length;
    const summary = index.summaries[model];

    ctx.el.innerHTML = html`
      <div class="kpis">
        <div class="kpi"><div class="label">Holdings</div><div class="value">${holdings.length}</div><div class="sub">${new Set(holdings.map((row) => row.sector)).size} sectors represented</div></div>
        <div class="kpi"><div class="label">Changes at this signal</div><div class="value">+${entering.length} / −${exiting.length}</div><div class="sub">Entering / exiting vs last rebalance</div></div>
        <div class="kpi"><div class="label">Implied turnover</div><div class="value">${pct(turnover, 0)}</div><div class="sub">Cost ≈ ${pct(cost, 2)} at ${index.ws.config.transaction_cost_bps} bps · history avg ${pct(summary.mean_turnover, 0)}</div></div>
        <div class="kpi"><div class="label">Average profile</div><div class="value">${num(avg('momentum'), 0)} <span class="muted" style="font-size:13px">mom.</span></div><div class="sub">Rel. strength ${num(avg('relative_strength'), 0)} · low risk ${num(avg('low_risk'), 0)}</div></div>
      </div>
      <div class="grid cols-main">
        ${raw(panel({ title: 'Target holdings', note: 'Weights if the book were rebalanced at the latest close.', body: '<div id="holdings"></div>', flush: true }))}
        <div class="stack">
          ${raw(panel({ title: 'Sector allocation', note: 'Portfolio weight against the equal-weight universe.', body: `
            <div class="legend"><span><i style="background:var(--series-1)"></i>Portfolio</span><span><i style="background:var(--bench)"></i>Universe</span></div>
            <div class="hbars">${sectors.map((row) => `
              <div class="hbar" title="${row.sector}: portfolio ${pct(row.held, 1)}, universe ${pct(row.universe, 1)}">
                <span class="name">${sectorShort(row.sector)}</span>
                <span class="track" style="height:14px">
                  <b style="left:0;top:0;height:6px;width:${(row.held / maxWeight) * 100}%;background:var(--series-1)"></b>
                  <b style="left:0;top:8px;height:5px;width:${(row.universe / maxWeight) * 100}%;background:var(--bench)"></b>
                </span>
                <span class="val ${toneClass(row.active)}">${pct(row.active, 0, { sign: true })}</span>
              </div>`).join('')}</div>
            <p class="note">Right column: active weight vs universe. The sleeve has no sector constraint, so concentration is a result of the ranking and worth watching.</p>` }))}
          ${raw(panel({ title: 'Entering', note: 'New to the book at this signal.', body: '<div id="entering"></div>', flush: true }))}
          ${raw(panel({ title: 'Exiting', note: 'Held at the last rebalance, now outside the top ranks.', body: '<div id="exiting"></div>', flush: true }))}
        </div>
      </div>`;

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
