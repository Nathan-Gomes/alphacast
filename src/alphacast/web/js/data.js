// Derived views of a workspace payload. Views never reach into the raw payload directly.

const MODEL_ORDER = ['momentum', 'ridge', 'elastic_net', 'random_forest', 'gradient_boosting'];

/** Colour follows the model, never its rank, so filters never repaint survivors. */
export function modelColor(model) {
  const slot = MODEL_ORDER.indexOf(model);
  return slot >= 0 ? `var(--series-${slot + 1})` : 'var(--bench)';
}

export const BENCH_COLOR = 'var(--bench)';

export function workspaceIndex(ws) {
  const byModel = (rows) => rows.reduce((groups, row) => {
    (groups[row.model] ||= []).push(row);
    return groups;
  }, {});
  const labels = Object.fromEntries(ws.models.map((model) => [model.id, model.label]));
  const featureLabels = Object.fromEntries(ws.features.map((feature) => [feature.id, feature.label]));
  const periods = byModel(ws.periods);
  Object.values(periods).forEach((rows) => rows.sort((a, b) => a.date.localeCompare(b.date)));
  return {
    ws,
    models: ws.models.map((model) => model.id),
    labels,
    featureLabels,
    summaries: Object.fromEntries(ws.summaries.map((row) => [row.model, row])),
    monitoring: Object.fromEntries(ws.monitoring.map((row) => [row.model, row])),
    periods,
    live: byModel(ws.live),
    importance: byModel(ws.feature_importance),
    regimes: byModel(ws.regimes),
    profiles: Object.fromEntries(ws.profiles.map((row) => [row.ticker, row])),
    tickers: ws.profiles.map((row) => row.ticker).sort(),
    sectors: [...new Set(ws.profiles.map((row) => row.sector))].sort(),
  };
}

/** The model with the strongest mean out-of-sample Rank IC. */
export function leadingModel(index) {
  return [...index.models].sort((a, b) => index.summaries[b].mean_rank_ic - index.summaries[a].mean_rank_ic)[0];
}

export function liveRows(index, model) {
  return (index.live[model] || []).map((row) => ({ ...index.profiles[row.ticker], ...row }));
}
