import { legend, lineChart, pairedBars } from '../charts.js';
import { modelColor } from '../data.js';
import { escapeHtml, html, num, pct, raw, rolling, toneClass } from '../format.js';
import { definition } from '../glossary.js';
import { dataTable } from '../table.js';
import { panel, statusBadge } from './parts.js';

// Relative features are a multiple of the day's median; others are raw percentages.
function medianCell(row, value) {
  if (row.relative_to_date_median) return `${num(value, 2)}× median`;
  if (row.feature === 'dollar_volume_20') return `$${Intl.NumberFormat('en-US', { notation: 'compact' }).format(value)}`;
  return pct(value, 1);
}

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
      <div class="grid model-cards" id="cards"></div>
      <div class="grid cols-main">
        ${raw(panel({ title: `Rolling ${window}-month Rank IC`, note: `${index.labels[model]}. The shaded band is the full-sample mean ± one standard error for a ${window}-month window; falling below it triggers “watch”, below zero triggers “degraded”.`, body: '<div id="roll-legend"></div><div id="rolling"></div>' }))}
        ${raw(panel({ title: 'Reliance drift', note: `Share of attribution over the last ${window} folds against the full history.`, body: '<div id="reliance"></div>' }))}
      </div>
      <div class="section-gap">${raw(panel({ title: 'Feature drift', note: 'Population stability index of feature values (dollar volume relative to each day\'s median): last 63 sessions against all earlier history. Under 0.10 stable, 0.10–0.25 moderate, above 0.25 shifted. Models see within-date ranks, so raw drift does not reach them directly, but it flags a market unlike most of the training data.', body: '<div id="drift"></div>', flush: true }))}</div>`;

    document.getElementById('cards').innerHTML = index.models.map((id) => {
      const row = index.monitoring[id];
      return `<button type="button" class="panel model-card" data-model="${id}" aria-pressed="${id === model}">
        <div class="model-card-head"><strong><span class="dot" style="background:${modelColor(id)}"></span>${escapeHtml(index.labels[id])}</strong>${statusBadge(row.status)}</div>
        <div class="model-card-value">${num(row.recent_mean_rank_ic, 3)}</div>
        <div class="model-card-sub">Recent IC · history ${num(row.historical_mean_rank_ic, 3)} (<span class="${toneClass(row.rank_ic_change)}">${num(row.rank_ic_change, 3, { sign: true })}</span>)</div>
        <div class="model-card-sub">${pct(row.recent_positive_ic_rate, 0)} positive · turnover ${pct(row.recent_turnover, 0)}</div>
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
    document.getElementById('reliance').innerHTML = `${pairedBars(top.map((row) => ({
      label: row.label, a: row.recent_importance, b: row.importance, value: (row.recent_importance - row.importance) * 100,
      title: `${row.label}: recent ${pct(row.recent_importance, 1)}, history ${pct(row.importance, 1)}`,
    })), { labelA: `Last ${window} folds`, labelB: 'Full history', colorA: modelColor(model), format: (value) => num(value, 1, { sign: true }) })}
      <p class="note">Right column: change in percentage points of attribution share.</p>`;

    dataTable(document.getElementById('drift'), {
      rows: index.ws.drift.map((row) => ({ ...row, label: index.featureLabels[row.feature] })),
      sortKey: 'psi',
      columns: [
        { key: 'label', label: 'Feature', render: (row) => (row.relative_to_date_median ? `${escapeHtml(row.label)} <span class="muted">(vs day median)</span>` : escapeHtml(row.label)) },
        { key: 'psi', label: 'PSI', num: true, title: definition('psi'), render: (row) => num(row.psi, 3) },
        { key: 'status', label: 'Status', sort: (row) => row.psi, render: (row) => statusBadge(row.status) },
        { key: 'reference_median', label: 'Historical median', num: true, render: (row) => medianCell(row, row.reference_median) },
        { key: 'recent_median', label: 'Recent median', num: true, render: (row) => medianCell(row, row.recent_median) },
        { key: 'median_shift_sd', label: 'Shift (SD)', num: true, render: (row) => num(row.median_shift_sd, 2, { sign: true }) },
      ],
    });
  },
};
