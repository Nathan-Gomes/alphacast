import { legend, lineChart } from '../charts.js';
import { modelColor } from '../data.js';
import { escapeHtml, html, num, pct, raw, rolling, toneClass } from '../format.js';
import { dataTable } from '../table.js';
import { panel, statusBadge } from './parts.js';

const RAW_PERCENT = new Set(['dollar_volume_20']);

export default {
  title: 'Monitoring',
  subtitle: () => 'Treat the model like production software: watch ranking quality, reliance and inputs drift',
  render(ctx) {
    const { index, model } = ctx;
    const window = index.ws.config.monitoring_window;
    const periods = index.periods[model];
    const ic = periods.map((row) => row.rank_ic);
    const historical = index.monitoring[model].historical_mean_rank_ic;
    const se = index.monitoring[model].standard_error;
    const importance = [...index.importance[model]].sort((a, b) => b.importance - a.importance);

    ctx.el.innerHTML = html`
      <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(200px,1fr));margin-bottom:16px" id="cards"></div>
      <div class="grid cols-main">
        ${raw(panel({ title: `Rolling ${window}-month Rank IC`, note: `${index.labels[model]}. The shaded band is the full-sample mean ± one standard error for a ${window}-month window; falling below it triggers “watch”, below zero triggers “degraded”.`, body: '<div id="roll-legend"></div><div id="rolling"></div>' }))}
        ${raw(panel({ title: 'Reliance drift', note: `Share of attribution over the last ${window} folds against the full history.`, body: '<div id="reliance"></div>' }))}
      </div>
      <div class="section-gap">${raw(panel({ title: 'Feature drift', note: 'Population stability index of raw feature values: last 63 sessions against all earlier history. Under 0.10 stable, 0.10–0.25 moderate, above 0.25 shifted. Models see within-date ranks, so raw drift does not reach them directly, but it flags a market unlike most of the training data.', body: '<div id="drift"></div>', flush: true }))}</div>`;

    document.getElementById('cards').innerHTML = index.models.map((id) => {
      const row = index.monitoring[id];
      return `<button type="button" class="panel model-card" data-model="${id}" style="text-align:left;padding:14px 16px;cursor:pointer;color:inherit;font:inherit;${id === model ? 'border-color:var(--accent)' : ''}">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:8px"><strong style="font-size:13px"><span class="dot" style="background:${modelColor(id)}"></span>${escapeHtml(index.labels[id])}</strong>${statusBadge(row.status)}</div>
        <div style="margin-top:10px;font-size:20px;font-weight:600;font-variant-numeric:tabular-nums">${num(row.recent_mean_rank_ic, 3)}</div>
        <div class="muted" style="font-size:12px">Recent IC · history ${num(row.historical_mean_rank_ic, 3)} (<span class="${toneClass(row.rank_ic_change)}">${num(row.rank_ic_change, 3, { sign: true })}</span>)</div>
        <div class="muted" style="font-size:12px;margin-top:4px">${pct(row.recent_positive_ic_rate, 0)} positive · turnover ${pct(row.recent_turnover, 0)}</div>
      </button>`;
    }).join('');
    document.querySelectorAll('.model-card').forEach((card) => card.addEventListener('click', () => ctx.setModel(card.dataset.model)));

    const series = [
      { label: `Rolling ${window}M IC`, color: modelColor(model), values: rolling(ic, window) },
      { label: 'Full-sample mean', color: 'var(--bench)', values: ic.map(() => historical), dash: true },
    ];
    document.getElementById('roll-legend').innerHTML = legend(series);
    lineChart(document.getElementById('rolling'), {
      dates: periods.map((row) => row.date), series, height: 280, baseline: 0,
      band: { lower: ic.map(() => historical - se), upper: ic.map(() => historical + se), color: 'var(--bench)' },
      yFormat: (value) => value.toFixed(2), tooltipFormat: (value) => value.toFixed(3),
      label: 'Rolling Rank IC against the full-sample mean band',
    });

    const top = importance.slice(0, 9);
    const max = Math.max(...top.flatMap((row) => [row.importance, row.recent_importance]), 0.01);
    document.getElementById('reliance').innerHTML = `
      <div class="legend"><span><i style="background:${modelColor(model)}"></i>Last ${window} folds</span><span><i style="background:var(--bench)"></i>Full history</span></div>
      <div class="hbars">${top.map((row) => `
        <div class="hbar" title="${escapeHtml(row.label)}: recent ${pct(row.recent_importance, 1)}, history ${pct(row.importance, 1)}">
          <span class="name">${escapeHtml(row.label)}</span>
          <span class="track" style="height:14px">
            <b style="left:0;top:0;height:6px;width:${(row.recent_importance / max) * 100}%;background:${modelColor(model)}"></b>
            <b style="left:0;top:8px;height:5px;width:${(row.importance / max) * 100}%;background:var(--bench)"></b>
          </span>
          <span class="val ${toneClass(row.recent_importance - row.importance)}">${num((row.recent_importance - row.importance) * 100, 1, { sign: true })}</span>
        </div>`).join('')}</div>
      <p class="note">Right column: change in percentage points of attribution share.</p>`;

    dataTable(document.getElementById('drift'), {
      rows: index.ws.drift.map((row) => ({ ...row, label: index.featureLabels[row.feature] })),
      sortKey: 'psi',
      columns: [
        { key: 'label', label: 'Feature' },
        { key: 'psi', label: 'PSI', num: true, render: (row) => num(row.psi, 3) },
        { key: 'status', label: 'Status', sort: (row) => row.psi, render: (row) => statusBadge(row.status) },
        { key: 'reference_median', label: 'Historical median', num: true, render: (row) => (RAW_PERCENT.has(row.feature) ? `$${Intl.NumberFormat('en-US', { notation: 'compact' }).format(row.reference_median)}` : pct(row.reference_median, 1)) },
        { key: 'recent_median', label: 'Recent median', num: true, render: (row) => (RAW_PERCENT.has(row.feature) ? `$${Intl.NumberFormat('en-US', { notation: 'compact' }).format(row.recent_median)}` : pct(row.recent_median, 1)) },
        { key: 'median_shift_sd', label: 'Shift (SD)', num: true, render: (row) => html`<span class="${toneClass(row.median_shift_sd)}">${num(row.median_shift_sd, 2, { sign: true })}</span>` },
      ],
    });
  },
};
