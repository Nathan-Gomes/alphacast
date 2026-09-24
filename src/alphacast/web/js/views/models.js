import { legend, lineChart } from '../charts.js';
import { BENCH_COLOR, modelColor, rankAgreement } from '../data.js';
import { cumulative, escapeHtml, html, num, pct, raw, toneClass } from '../format.js';
import { definition } from '../glossary.js';
import { dataTable } from '../table.js';
import { panel, statusBadge } from './parts.js';

function heatGrid(index) {
  const features = index.ws.features.map((feature) => feature.id);
  const values = index.models.map((model) => Object.fromEntries(index.importance[model].map((row) => [row.feature, row.importance])));
  const max = Math.max(...values.flatMap((row) => Object.values(row)), 0.01);
  const cells = index.models.map((model, row) => `
    <div class="rowhead"><span class="dot" style="background:${modelColor(model)}"></span>${escapeHtml(index.labels[model])}</div>
    ${features.map((feature) => {
      const value = values[row][feature] || 0;
      const step = value / max;
      const shade = step > 0.66 ? 3 : step > 0.33 ? 2 : step > 0.08 ? 1 : 0;
      return `<div class="cell s${shade}" title="${escapeHtml(index.labels[model])} · ${escapeHtml(index.featureLabels[feature])}: ${pct(value, 1)} of attribution">${value >= 0.005 ? Math.round(value * 100) : ''}</div>`;
    }).join('')}`).join('');
  return `<div class="table-wrap"><div class="heatgrid" style="grid-template-columns:150px repeat(${features.length}, minmax(44px, 1fr));min-width:${150 + features.length * 48}px">
    <div></div>${features.map((feature) => `<div class="colhead" title="${escapeHtml(index.featureLabels[feature])}" style="writing-mode:vertical-rl;transform:rotate(180deg);height:110px;text-align:left">${escapeHtml(index.featureLabels[feature])}</div>`).join('')}
    ${cells}</div></div>`;
}

function agreementGrid(index) {
  const ids = index.models;
  const cells = ids.map((row) => `
    <div class="rowhead"><span class="dot" style="background:${modelColor(row)}"></span>${escapeHtml(index.labels[row])}</div>
    ${ids.map((col) => {
      const rho = rankAgreement(index, row, col);
      const shade = rho > 0.8 ? 3 : rho > 0.5 ? 2 : rho > 0.2 ? 1 : 0;
      return `<div class="cell s${shade}" title="${escapeHtml(index.labels[row])} vs ${escapeHtml(index.labels[col])}: Spearman ${num(rho, 2)}">${num(rho, 2)}</div>`;
    }).join('')}`).join('');
  return `<div class="table-wrap"><div class="heatgrid" style="grid-template-columns:150px repeat(${ids.length}, minmax(56px, 1fr));min-width:${150 + ids.length * 60}px">
    <div></div>${ids.map((id) => `<div class="colhead">${escapeHtml(index.labels[id])}</div>`).join('')}${cells}</div></div>`;
}

export default {
  title: 'Models',
  subtitle: () => 'Every model on the identical walk-forward sequence, costs and portfolio rule',
  render(ctx) {
    const { index, model } = ctx;
    const rows = index.models.map((id) => ({ ...index.summaries[id], label: index.labels[id], status: index.monitoring[id].status }));
    const first = index.periods[index.models[0]];
    const dates = first.map((row) => row.date);

    ctx.el.innerHTML = html`
      ${raw(panel({ title: 'Model comparison', note: 'Out-of-sample only. Select a row to make that model active across the workstation.', body: '<div id="compare"></div>', flush: true }))}
      <div class="grid cols-2 section-gap">
        ${raw(panel({ title: 'Cumulative Rank IC', note: 'Sum of monthly Rank IC. A steady upward slope is a persistent signal; a flat stretch is a period without skill.', body: '<div id="ic-legend"></div><div id="ic"></div>' }))}
        ${raw(panel({ title: 'Net growth by model', note: 'Top-ranked sleeve after costs, against the equal-weight universe.', body: '<div id="growth-legend"></div><div id="growth"></div>' }))}
      </div>
      <div class="section-gap">${raw(panel({ title: 'Model specifications', note: 'Declared before any result and identical in every fold. Read from the estimators the research builds.', body: '<div id="specs"></div>', flush: true }))}</div>
      <div class="section-gap">${raw(panel({ title: 'How much the models agree today', note: 'Spearman correlation between each pair of models\' rankings at the latest close. Low agreement means the models are finding different stocks, not the same bet in different clothes.', body: '<div id="agreement"></div>' }))}</div>
      <div class="section-gap">${raw(panel({ title: 'What each model relies on', note: 'Average share of attribution per feature across folds (percent). Reliance describes the model, not causality.', body: '<div id="heat"></div>' }))}</div>`;

    dataTable(document.getElementById('compare'), {
      rows,
      sortKey: 'mean_rank_ic',
      rowClass: (row) => (row.model === model ? 'selected' : ''),
      onRowClick: (row) => ctx.setModel(row.model),
      columns: [
        { key: 'label', label: 'Model', render: (row) => html`<span class="dot" style="background:${raw(modelColor(row.model))}"></span>${row.label}` },
        { key: 'mean_rank_ic', label: 'Mean IC', num: true, title: definition('rank_ic'), render: (row) => num(row.mean_rank_ic, 3) },
        { key: 'ic_t_stat', label: 'IC t-stat', num: true, title: definition('t_stat'), render: (row) => num(row.ic_t_stat, 2) },
        { key: 'ic_ci_low', label: 'IC 95% interval', num: true, title: definition('ic_ci'), render: (row) => (Number.isFinite(row.ic_ci_low) ? html`<span class="${row.ic_ci_low > 0 ? 'pos' : ''}">${num(row.ic_ci_low, 3)} to ${num(row.ic_ci_high, 3)}</span>` : '—') },
        { key: 'p_value_holm', label: 'p (Holm)', num: true, title: definition('holm'), render: (row) => html`<span class="${row.p_value_holm < 0.05 ? 'pos' : ''}">${num(row.p_value_holm, 3)}</span>` },
        { key: 'positive_ic_rate', label: 'IC > 0', num: true, render: (row) => pct(row.positive_ic_rate, 0) },
        { key: 'mean_q1_q5_spread', label: 'Q1 − Q5', num: true, title: 'Average monthly sector-relative spread between top and bottom quintiles', render: (row) => pct(row.mean_q1_q5_spread, 2) },
        { key: 'gross_sharpe', label: 'Gross SR', num: true, render: (row) => num(row.gross_sharpe, 2) },
        { key: 'net_sharpe', label: 'Net SR', num: true, render: (row) => num(row.net_sharpe, 2) },
        { key: 'information_ratio', label: 'Info ratio', num: true, title: definition('info_ratio'), render: (row) => num(row.information_ratio, 2) },
        { key: 'mean_turnover', label: 'Turnover', num: true, title: definition('turnover'), render: (row) => pct(row.mean_turnover, 0) },
        { key: 'beta', label: 'Beta', num: true, title: definition('beta'), render: (row) => num(row.beta, 2) },
        { key: 'alpha_annualized', label: 'Alpha/yr', num: true, title: definition('alpha'), render: (row) => html`<span class="${toneClass(row.alpha_annualized)}">${pct(row.alpha_annualized, 1, { sign: true })}</span>` },
        { key: 'max_drawdown', label: 'Max DD', num: true, render: (row) => pct(row.max_drawdown, 1) },
        { key: 'status', label: 'Health', render: (row) => statusBadge(row.status) },
      ],
    });

    const icSeries = index.models.map((id) => {
      let total = 0;
      return { label: index.labels[id], color: modelColor(id), values: index.periods[id].map((row) => (total += row.rank_ic)), width: id === model ? 2.6 : 1.6 };
    });
    document.getElementById('ic-legend').innerHTML = legend(icSeries);
    lineChart(document.getElementById('ic'), {
      dates, series: icSeries, height: 280, baseline: 0, yFormat: (value) => value.toFixed(1), tooltipFormat: (value) => value.toFixed(2),
      label: 'Cumulative Rank IC by model',
    });
    const growthSeries = [
      ...index.models.map((id) => ({ label: index.labels[id], color: modelColor(id), values: cumulative(index.periods[id].map((row) => row.net_return)), width: id === model ? 2.6 : 1.6 })),
      { label: 'Universe', color: BENCH_COLOR, values: cumulative(first.map((row) => row.benchmark_return)), dash: true },
    ];
    document.getElementById('growth-legend').innerHTML = legend(growthSeries);
    lineChart(document.getElementById('growth'), {
      dates, series: growthSeries, height: 280, baseline: 1, yFormat: (value) => `$${value.toFixed(1)}`, tooltipFormat: (value) => `$${value.toFixed(2)}`,
      label: 'Net growth of one dollar by model',
    });
    document.getElementById('heat').innerHTML = heatGrid(index);
    document.getElementById('agreement').innerHTML = agreementGrid(index);
    const specs = (ctx.catalog?.model_specs || []).filter((spec) => index.models.includes(spec.id));
    dataTable(document.getElementById('specs'), {
      rows: specs, empty: 'Specifications load with the catalog.',
      columns: [
        { key: 'id', label: 'Model', sortable: false, render: (row) => html`<span class="dot" style="background:${raw(modelColor(row.id))}"></span>${index.labels[row.id]}` },
        { key: 'description', label: 'What it is', sortable: false, render: (row) => html`<span class="spec-text">${row.description}</span>` },
        { key: 'params', label: 'Hyperparameters', sortable: false, render: (row) => {
          const entries = Object.entries(row.params).filter(([key]) => key !== 'estimator');
          return entries.length
            ? `<span class="mono spec-text">${entries.map(([key, value]) => `${escapeHtml(key)}=${escapeHtml(value ?? 'None')}`).join(' · ')}</span>`
            : '<span class="muted">None</span>';
        } },
      ],
    });
  },
};
