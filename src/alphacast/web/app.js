const byId = (id) => document.getElementById(id);
const form = byId('research-form');
const status = byId('run-status');
const today = new Date().toISOString().slice(0, 10);
byId('end').value = today;

let currentRun = null;

const pct = (value, digits = 2) => `${(value * 100).toFixed(digits)}%`;
const decimal = (value, digits = 3) => Number(value).toFixed(digits);
const title = (value) => value.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
const safe = (value) => String(value).replace(/[&<>"']/g, (character) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;',
}[character]));

async function loadUniverse() {
  const response = await fetch('/api/universe');
  const data = await response.json();
  byId('tickers').value = Object.keys(data.tickers).join(', ');
}

function requestPayload() {
  return {
    source: document.querySelector('input[name="source"]:checked').value,
    tickers: byId('tickers').value.split(',').map((ticker) => ticker.trim()).filter(Boolean),
    start: byId('start').value,
    end: byId('end').value,
    top_n: Number(byId('top-n').value),
    transaction_cost_bps: Number(byId('cost-bps').value),
    models: [...document.querySelectorAll('.models input:checked')].map((input) => input.value),
  };
}

function quality(data) {
  const items = [
    [data.source === 'yahoo' ? 'Yahoo history' : 'Synthetic panel', 'Data source'],
    [data.accepted_tickers, 'Securities accepted'],
    [data.sessions.toLocaleString(), 'Trading sessions'],
    [`${data.first_date} → ${data.last_date}`, 'Historical coverage'],
    [data.missing_observations.toLocaleString(), 'Missing ticker-date cells'],
  ];
  byId('quality').innerHTML = items.map(([value, label]) => `<div><strong>${value}</strong><span>${label}</span></div>`).join('');
}

function renderSummary(rows) {
  byId('summary-body').innerHTML = rows.map((row) => `<tr><td>${safe(title(row.model))}</td><td>${decimal(row.mean_rank_ic)}</td><td>${decimal(row.ic_information_ratio, 2)}</td><td>${pct(row.positive_ic_rate, 1)}</td><td>${pct(row.mean_q1_q5_spread)}</td><td>${decimal(row.net_sharpe, 2)}</td><td>${pct(row.mean_turnover, 1)}</td><td>${pct(row.net_terminal_growth, 1)}</td></tr>`).join('');
}

function renderMonitoring(rows) {
  byId('monitoring-body').innerHTML = rows.map((row) => `<tr><td>${safe(title(row.model))}</td><td>${decimal(row.recent_mean_rank_ic)}</td><td>${decimal(row.rank_ic_change)}</td><td>${pct(row.recent_positive_ic_rate, 1)}</td></tr>`).join('');
}

function renderRegimes(rows) {
  byId('regime-body').innerHTML = rows.map((row) => `<tr><td>${safe(title(row.model))}</td><td>${safe(row.regime)}</td><td>${decimal(row.mean_rank_ic)}</td><td>${pct(row.mean_q1_q5_spread)}</td></tr>`).join('');
}

function path(points, width, height, padding) {
  const min = Math.min(...points.map((point) => point.value));
  const max = Math.max(...points.map((point) => point.value));
  const range = Math.max(max - min, 0.01);
  return points.map((point, index) => {
    const x = padding + index * ((width - padding * 2) / Math.max(points.length - 1, 1));
    const y = height - padding - ((point.value - min) / range) * (height - padding * 2);
    return `${index ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
}

function renderChart(model) {
  const rows = currentRun.periods.filter((row) => row.model === model);
  let strategy = 1;
  let benchmark = 1;
  const strategyPoints = [{ value: strategy }];
  const benchmarkPoints = [{ value: benchmark }];
  rows.forEach((row) => {
    strategy *= 1 + row.net_return;
    benchmark *= 1 + row.benchmark_return;
    strategyPoints.push({ value: strategy });
    benchmarkPoints.push({ value: benchmark });
  });
  const all = [...strategyPoints, ...benchmarkPoints];
  const min = Math.min(...all.map((point) => point.value));
  const max = Math.max(...all.map((point) => point.value));
  const svg = byId('equity-chart');
  svg.innerHTML = `<line x1="42" x2="42" y1="18" y2="264" stroke="#344453"/><line x1="42" x2="875" y1="264" y2="264" stroke="#344453"/><text x="42" y="286" fill="#9aabb8" font-size="12">${rows[0]?.date ?? ''}</text><text x="780" y="286" fill="#9aabb8" font-size="12">${rows.at(-1)?.date ?? ''}</text><text x="48" y="35" fill="#9aabb8" font-size="12">Range ${pct(min - 1, 1)} to ${pct(max - 1, 1)}</text><path d="${path(benchmarkPoints, 900, 282, 42)}" fill="none" stroke="#73a9ff" stroke-width="3"/><path d="${path(strategyPoints, 900, 282, 42)}" fill="none" stroke="#55d6a5" stroke-width="3"/>`;
}

function renderImportance(model) {
  const rows = currentRun.feature_importance.filter((row) => row.model === model).slice(0, 7);
  const max = Math.max(...rows.map((row) => row.importance), 0.00001);
  byId('importance').innerHTML = rows.map((row) => `<li><div>${safe(title(row.feature))}<span style="width:${(row.importance / max) * 100}%"></span></div><em>${decimal(row.importance, 3)}</em></li>`).join('');
}

function renderRankings(model) {
  const rows = currentRun.latest_rankings.filter((row) => row.model === model).slice(0, 15);
  byId('ranking-body').innerHTML = rows.map((row) => `<tr><td>${row.rank}</td><td>${safe(row.ticker)}</td><td>${safe(row.sector)}</td><td>${decimal(row.score, 4)}</td><td>${pct(row.momentum_12_1)}</td><td>${pct(row.volatility_20, 1)}</td></tr>`).join('');
}

function render(data) {
  currentRun = data;
  byId('results').hidden = false;
  quality(data.quality);
  renderSummary(data.summaries);
  renderMonitoring(data.monitoring);
  renderRegimes(data.regimes);
  byId('run-label').textContent = `${title(data.source)} · ${data.config.horizon_sessions}-session horizon · ${data.config.embargo_sessions}-session embargo`;
  const select = byId('model-select');
  select.innerHTML = data.summaries.map((row) => `<option value="${safe(row.model)}">${safe(title(row.model))}</option>`).join('');
  const update = () => { renderChart(select.value); renderImportance(select.value); renderRankings(select.value); };
  select.onchange = update;
  update();
  byId('results').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const payload = requestPayload();
  if (!payload.models.length) { status.textContent = 'Select at least one model.'; return; }
  const button = byId('run-button');
  button.disabled = true;
  status.textContent = payload.source === 'yahoo' ? 'Downloading Yahoo history and running embargoed walk-forward folds…' : 'Generating the deterministic panel and running embargoed walk-forward folds…';
  try {
    const response = await fetch('/api/research', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Research run failed.');
    render(data);
    status.textContent = `Completed ${data.summaries[0].folds} out-of-sample folds per selected model. Read the controls and limits beside the results.`;
  } catch (error) {
    status.textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

loadUniverse();
