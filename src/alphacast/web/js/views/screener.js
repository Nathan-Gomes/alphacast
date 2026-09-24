import { liveRows } from '../data.js';
import { downloadFile, html, pct, sectorShort, toCsv, toneClass, num, raw } from '../format.js';
import { dataTable } from '../table.js';
import { heatCell, pctBar, rankChange, tickerLink } from './parts.js';
import { bindStars, starButton, watchlist } from '../watchlist.js';

// Filters survive re-renders (model switch, resize) for the session.
const filters = { query: '', sector: '', quintile: '', portfolio: false, watch: false };

export default {
  title: 'Screener',
  subtitle: (ctx) => `Every security in the universe, ranked by ${ctx.index.labels[ctx.model]}`,
  render(ctx) {
    const { index, model } = ctx;
    const rows = liveRows(index, model);
    const hasPrediction = model !== 'momentum';

    ctx.el.innerHTML = html`
      <section class="panel">
        <div class="filters" role="search">
          <input type="search" id="q" placeholder="Search ticker or sector" aria-label="Search ticker or sector" value="${filters.query}">
          <select id="sector" aria-label="Sector"><option value="">All sectors</option>${index.sectors.map((sector) => raw(html`<option value="${sector}" ${raw(filters.sector === sector ? 'selected' : '')}>${sector}</option>`))}</select>
          <select id="quintile" aria-label="Quintile"><option value="">All quintiles</option>${[1, 2, 3, 4, 5].map((q) => raw(`<option value="${q}" ${String(q) === filters.quintile ? 'selected' : ''}>Q${q}${q === 1 ? ' (top)' : q === 5 ? ' (bottom)' : ''}</option>`))}</select>
          <label class="check"><input type="checkbox" id="portfolio" ${raw(filters.portfolio ? 'checked' : '')}> In portfolio</label>
          <label class="check"><input type="checkbox" id="watch" ${raw(filters.watch ? 'checked' : '')}> Watchlist</label>
          <span class="spacer"></span>
          <span class="count" id="count"></span>
          <button class="button small" id="csv" type="button">Export CSV</button>
        </div>
        <div class="scroll-table" id="table"></div>
      </section>
      <p class="note">Score percentile ranks the model output within today's cross-section (100 = most attractive). Factor columns are descriptive percentiles: momentum (6M, 12-1, 50/200 MA), relative strength (3M vs market and sector), low risk (inverse volatility and drawdown), liquidity (20-day dollar volume). They describe a profile; they are not the model's weights.${hasPrediction ? ' Model output is the predicted 20-session return relative to the sector, most useful as an ordering.' : ''}</p>`;

    const columns = [
      { key: 'star', label: '', sortable: false, render: (row) => starButton(row.ticker) },
      { key: 'rank', label: 'Rank', num: true },
      { key: 'ticker', label: 'Ticker', render: (row) => tickerLink(row.ticker) },
      { key: 'sector', label: 'Sector', render: (row) => html`<span class="sector">${sectorShort(row.sector)}</span>` },
      { key: 'percentile', label: 'Score pct.', num: true, render: (row) => pctBar(row.percentile) },
      ...(hasPrediction ? [{ key: 'predicted_relative_return', label: 'Model output', num: true, title: 'Predicted 20-session sector-relative return', render: (row) => html`<span class="${toneClass(row.predicted_relative_return)}">${pct(row.predicted_relative_return, 2, { sign: true })}</span>` }] : []),
      { key: 'quintile', label: 'Q', num: true, render: (row) => `Q${row.quintile}` },
      { key: 'rank_change', label: 'Δ Rank', num: true, render: (row) => rankChange(row.rank_change) },
      { key: 'momentum', label: 'Momentum', num: true, render: (row) => heatCell(row.momentum) },
      { key: 'relative_strength', label: 'Rel. str.', num: true, render: (row) => heatCell(row.relative_strength) },
      { key: 'low_risk', label: 'Low risk', num: true, render: (row) => heatCell(row.low_risk) },
      { key: 'liquidity', label: 'Liquidity', num: true, render: (row) => heatCell(row.liquidity) },
      { key: 'return_1d', label: '1D', num: true, render: (row) => html`<span class="${toneClass(row.return_1d)}">${pct(row.return_1d, 2, { sign: true })}</span>` },
      { key: 'momentum_12_1', label: '12-1 mom.', num: true, render: (row) => html`<span class="${toneClass(row.momentum_12_1)}">${pct(row.momentum_12_1, 1, { sign: true })}</span>` },
      { key: 'volatility_20', label: '20D vol', num: true, render: (row) => pct(row.volatility_20, 1) },
      { key: 'in_portfolio', label: 'Held', num: true, sort: (row) => (row.in_portfolio ? 1 : 0), render: (row) => (row.in_portfolio ? '<span class="tag">Held</span>' : '') },
    ];

    const filtered = () => rows.filter((row) => {
      const query = filters.query.trim().toUpperCase();
      if (query && !row.ticker.includes(query) && !row.sector.toUpperCase().includes(query)) return false;
      if (filters.sector && row.sector !== filters.sector) return false;
      if (filters.quintile && String(row.quintile) !== filters.quintile) return false;
      if (filters.portfolio && !row.in_portfolio) return false;
      if (filters.watch && !watchlist.has(row.ticker)) return false;
      return true;
    });

    const table = dataTable(document.getElementById('table'), {
      columns, rows: filtered(), sortKey: 'rank', sortDir: 'asc',
      onRowClick: (row) => ctx.navigate(`#/security/${row.ticker}`),
      rowClass: (row) => (row.in_portfolio ? 'held' : ''),
      afterRender: (element) => bindStars(element, () => { if (filters.watch) refresh(); }),
      empty: filters.watch && !watchlist.all().length ? 'Your watchlist is empty. Star a ticker to add it.' : 'No securities match these filters.',
    });
    const count = document.getElementById('count');
    const refresh = () => {
      const visible = filtered();
      table.update(visible);
      count.textContent = `${visible.length} of ${rows.length}`;
    };
    count.textContent = `${filtered().length} of ${rows.length}`;

    const bind = (id, key, event = 'change', read = (element) => element.value) => {
      document.getElementById(id).addEventListener(event, (e) => { filters[key] = read(e.target); refresh(); });
    };
    bind('q', 'query', 'input');
    bind('sector', 'sector');
    bind('quintile', 'quintile');
    bind('portfolio', 'portfolio', 'change', (element) => element.checked);
    bind('watch', 'watch', 'change', (element) => element.checked);
    document.getElementById('csv').addEventListener('click', () => {
      const exportColumns = [
        { key: 'rank', label: 'rank' }, { key: 'ticker', label: 'ticker' }, { key: 'sector', label: 'sector' },
        { key: 'percentile', label: 'score_percentile', csv: (row) => num(row.percentile, 2) },
        { key: 'predicted_relative_return', label: 'model_output' }, { key: 'quintile', label: 'quintile' },
        { key: 'rank_change', label: 'rank_change' }, { key: 'momentum', label: 'momentum_pct' },
        { key: 'relative_strength', label: 'relative_strength_pct' }, { key: 'low_risk', label: 'low_risk_pct' },
        { key: 'liquidity', label: 'liquidity_pct' }, { key: 'in_portfolio', label: 'in_portfolio' },
      ];
      downloadFile(`alphacast-${model}-${index.ws.signal_date}.csv`, toCsv(table.rows(), exportColumns));
    });
  },
};
