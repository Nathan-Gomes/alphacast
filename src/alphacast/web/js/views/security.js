import { api } from '../api.js';
import { columnChart, hbars, legend, lineChart } from '../charts.js';
import { liveRows, modelColor } from '../data.js';
import { html, isNum, mean, money, num, pct, raw, toneClass } from '../format.js';
import { dataTable } from '../table.js';
import { heatCell, panel } from './parts.js';

const PERCENT_FEATURES = new Set(['return_21', 'return_63', 'return_126', 'momentum_12_1', 'volatility_20', 'volatility_60', 'downside_volatility_60', 'drawdown_252', 'distance_high_252', 'ma_ratio_50_200', 'volume_ratio_20', 'market_relative_63', 'sector_relative_63']);

function featureValue(feature, value) {
  if (!isNum(value)) return '—';
  if (feature === 'dollar_volume_20') return `$${Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(value)}`;
  return PERCENT_FEATURES.has(feature) ? pct(value, 1, { sign: feature.includes('return') || feature.includes('relative') || feature.includes('momentum') }) : num(value, 2);
}

let lastTicker = null;

export default {
  title: 'Security',
  subtitle: (ctx) => 'Why a security ranks where it does, and how its past ranks played out',
  async render(ctx) {
    const { index, model } = ctx;
    const requested = (ctx.params[0] || lastTicker || liveRows(index, model)[0]?.ticker || '').toUpperCase();
    if (!index.profiles[requested]) {
      ctx.el.innerHTML = html`<div class="loading"><p>${requested || 'That security'} is not in this workspace.</p><a class="button" href="#/screener">Open the screener</a></div>`;
      return;
    }
    const ticker = requested;
    lastTicker = ticker;
    if (!ctx.params[0]) history.replaceState(null, '', `#/security/${ticker}`);
    const profile = index.profiles[ticker];
    const live = index.live[model].find((row) => row.ticker === ticker);
    const total = index.live[model].length;

    ctx.el.innerHTML = html`
      <div class="sec-head">
        <div><h2>${ticker}</h2><div class="meta">${profile.sector}</div></div>
        <div><div class="price">${money(profile.price)}</div><div class="${toneClass(profile.return_1d)}">${pct(profile.return_1d, 2, { sign: true })} on the day</div></div>
        <label class="field picker"><span>Jump to security</span>
          <input id="picker" type="text" list="tickers" autocomplete="off" spellcheck="false" placeholder="Ticker" aria-label="Jump to ticker">
          <datalist id="tickers">${index.tickers.map((item) => raw(`<option value="${item}">`))}</datalist>
        </label>
      </div>
      <div class="kpis">
        <div class="kpi"><div class="label">Rank · ${index.labels[model]}</div><div class="value">${live.rank} <span class="muted" style="font-size:14px">/ ${total}</span></div><div class="sub">Quintile Q${live.quintile}</div></div>
        <div class="kpi"><div class="label">Score percentile</div><div class="value">${num(live.percentile, 0)}</div><div class="sub">${isNum(live.previous_rank) ? `Rank ${live.previous_rank} at last rebalance` : 'Unranked at last rebalance'}</div></div>
        <div class="kpi"><div class="label">Model output</div><div class="value ${toneClass(live.predicted_relative_return)}">${model === 'momentum' ? '—' : pct(live.predicted_relative_return, 2, { sign: true })}</div><div class="sub">Predicted 20-session return vs sector</div></div>
        <div class="kpi"><div class="label">Portfolio</div><div class="value">${live.in_portfolio ? 'Held' : 'Not held'}</div><div class="sub">${live.in_portfolio ? `${pct(live.weight, 1)} weight${live.was_held ? '' : ' · entering'}` : live.was_held ? 'Exiting at this signal' : `Top ${index.ws.config.top_n} are held`}</div></div>
      </div>
      <div class="grid cols-2">
        ${raw(panel({ title: 'Price', note: 'Weekly adjusted close.', body: '<div id="price"></div>' }))}
        ${raw(panel({ title: 'Why it ranks here', note: 'Score change when each feature is set to today\'s cross-sectional median. Positive pushes the rank up.', body: '<div id="attribution"><div class="skeleton" style="height:220px"></div></div>' }))}
      </div>
      <div class="grid cols-2 section-gap">
        ${raw(panel({ title: 'Rank history and outcomes', note: 'Score percentile at each monthly rebalance and the sector-relative return realised over the next 20 sessions.', body: '<div id="rank-legend"></div><div id="rank-history"></div><div id="realized"></div><p class="note" id="hit-note"></p>' }))}
        <div class="stack">
          ${raw(panel({ title: 'Rank under every model', note: 'Select a model to make it active.', body: '<div class="model-ranks" id="model-ranks"></div>' }))}
          ${raw(panel({ title: 'Factor profile', note: 'Cross-sectional percentiles today (100 = strongest).', body: '<div id="factors"></div>' }))}
        </div>
      </div>
      <div class="section-gap">${raw(panel({ title: 'Feature values', note: 'Raw trailing inputs at the signal date and where they sit in the universe.', body: '<div class="table-wrap" id="features"></div>', flush: false }))}</div>`;

    const picker = document.getElementById('picker');
    picker.addEventListener('change', () => {
      const value = picker.value.trim().toUpperCase();
      if (index.profiles[value]) ctx.navigate(`#/security/${value}`);
      else ctx.toast(`${value} is not in this workspace.`);
    });

    document.getElementById('model-ranks').innerHTML = index.models.map((id) => {
      const row = index.live[id].find((item) => item.ticker === ticker);
      return `<button type="button" class="model-rank${id === model ? ' active' : ''}" data-model="${id}" style="text-align:left;background:none;cursor:pointer;color:inherit;font:inherit">
        <span><i class="dot" style="background:${modelColor(id)}"></i>${index.labels[id]}</span><strong>#${row.rank}</strong> <span style="display:inline">Q${row.quintile}</span></button>`;
    }).join('');
    document.querySelectorAll('.model-rank').forEach((button) => button.addEventListener('click', () => ctx.setModel(button.dataset.model)));

    document.getElementById('factors').innerHTML = hbars([
      { label: 'Momentum', value: profile.momentum },
      { label: 'Relative strength', value: profile.relative_strength },
      { label: 'Low risk', value: profile.low_risk },
      { label: 'Liquidity', value: profile.liquidity },
    ], { format: (value) => value.toFixed(0) });

    let detail;
    try {
      detail = await api.security(ctx.runId, ticker);
    } catch (error) {
      document.getElementById('attribution').innerHTML = html`<p class="empty">${error.message}</p>`;
      return;
    }
    if (lastTicker !== ticker || !document.getElementById('price')) return;

    lineChart(document.getElementById('price'), {
      dates: detail.prices.dates,
      series: [{ label: ticker, color: 'var(--series-1)', values: detail.prices.close, area: true }],
      height: 250, yFormat: (value) => `$${value >= 1000 ? value.toFixed(0) : value.toFixed(value >= 100 ? 0 : 2)}`,
      tooltipFormat: (value) => money(value), label: `${ticker} weekly adjusted close`,
    });

    const attribution = [...(detail.attribution[model] || [])].sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution));
    const scale = model === 'momentum' ? 100 : 10_000;
    document.getElementById('attribution').innerHTML = attribution.every((row) => row.contribution === 0)
      ? '<p class="empty">No feature moves this score.</p>'
      : hbars(attribution.slice(0, 10).map((row) => ({
        label: index.featureLabels[row.feature], value: row.contribution * scale,
        title: `${index.featureLabels[row.feature]}: ${featureValue(row.feature, row.value)} (${num(row.percentile, 0)} pct.)`,
      })), { signed: true, format: (value) => `${value > 0 ? '+' : ''}${value.toFixed(model === 'momentum' ? 0 : 1)}`, color: 'var(--series-1)', negativeColor: 'var(--series-2)' })
        + `<p class="note">Units: ${model === 'momentum' ? 'percentile points of the momentum score' : 'basis points of predicted relative return'}. ${model === 'ridge' || model === 'elastic_net' ? 'For linear models this decomposition is exact.' : model === 'momentum' ? 'The baseline uses one input by design.' : 'For tree models it is a local approximation that ignores interactions.'}</p>`;

    const past = detail.history[model] || [];
    document.getElementById('rank-legend').innerHTML = legend([{ label: 'Score percentile', color: modelColor(model) }]);
    lineChart(document.getElementById('rank-history'), {
      dates: past.map((row) => row.date),
      series: [{ label: 'Score percentile', color: modelColor(model), values: past.map((row) => row.percentile) }],
      height: 170, baseline: 50, yFormat: (value) => value.toFixed(0), label: `${ticker} score percentile by rebalance`,
    });
    columnChart(document.getElementById('realized'), {
      dates: past.map((row) => row.date), values: past.map((row) => row.realized), height: 150,
      yFormat: (value) => pct(value, 0), positive: 'var(--pos)', negative: 'var(--neg)',
      label: `${ticker} realised 20-session sector-relative return by rebalance`,
      tooltipRows: (i) => [
        { label: 'Score percentile', value: num(past[i].percentile, 0) },
        { label: 'Quintile', value: `Q${past[i].quintile}` },
        { label: 'Realised vs sector', value: pct(past[i].realized, 2, { sign: true }) },
        { label: 'Held', value: past[i].held ? 'Yes' : 'No' },
      ],
    });
    const top = past.filter((row) => row.quintile === 1);
    const bottom = past.filter((row) => row.quintile === 5);
    const hit = (rows) => (rows.length ? `${pct(rows.filter((row) => row.realized > 0).length / rows.length, 0)} beat their sector (avg ${pct(mean(rows.map((row) => row.realized)), 2, { sign: true })})` : 'no occurrences');
    document.getElementById('hit-note').textContent = `When ${ticker} was in Q1 (${top.length} months): ${hit(top)}. In Q5 (${bottom.length} months): ${hit(bottom)}. One security's history is a small sample.`;

    dataTable(document.getElementById('features'), {
      rows: attribution.map((row) => ({ ...row, label: index.featureLabels[row.feature] })),
      sortKey: 'contribution',
      columns: [
        { key: 'label', label: 'Feature' },
        { key: 'value', label: 'Value', num: true, render: (row) => featureValue(row.feature, row.value) },
        { key: 'percentile', label: 'Universe pct.', num: true, render: (row) => heatCell(row.percentile) },
        { key: 'contribution', label: 'Contribution', num: true, sort: (row) => row.contribution, render: (row) => html`<span class="${toneClass(row.contribution)}">${num(row.contribution * scale, 1, { sign: true })}</span>` },
      ],
    });
  },
};

