// AlphaCast workstation shell: state, routing, workspace loading, run polling.

import { api } from './api.js';
import { hideTooltip, showTooltip, tooltipHtml } from './charts.js';
import { DEFINITIONS } from './glossary.js';
import { initPalette, initShortcutHelp } from './palette.js';
import { workspaceIndex, leadingModel } from './data.js';
import { cadence, date, escapeHtml, html, int } from './format.js';
import overview from './views/overview.js';
import screener from './views/screener.js';
import security from './views/security.js';
import portfolio from './views/portfolio.js';
import backtest from './views/backtest.js';
import models from './views/models.js';
import diagnostics from './views/diagnostics.js';
import monitoring from './views/monitoring.js';
import runs from './views/runs.js';

const VIEWS = { overview, screener, security, portfolio, backtest, models, diagnostics, monitoring, runs };
const $ = (id) => document.getElementById(id);

const storage = {
  get(key) { try { return localStorage.getItem(`alphacast.${key}`); } catch { return null; } },
  set(key, value) { try { localStorage.setItem(`alphacast.${key}`, value); } catch { /* private mode */ } },
};

const state = {
  catalog: null,
  runs: [],
  runId: storage.get('run') || 'default',
  record: null,
  index: null,
  model: storage.get('model'),
  pollTimer: null,
  watching: new Set(),
};

export function toast(message, timeout = 4200) {
  const element = $('toast');
  element.textContent = message;
  element.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { element.hidden = true; }, timeout);
}

function parseRoute() {
  const [path, search = ''] = location.hash.replace(/^#\/?/, '').split('?');
  const [view, ...params] = path.split('/').filter(Boolean);
  return {
    view: VIEWS[view] ? view : 'overview',
    params: params.map(decodeURIComponent),
    query: Object.fromEntries(new URLSearchParams(search)),
  };
}

/** Keep the model and run in the address so a copied link opens the same view. */
function syncAddress() {
  if (!state.index) return;
  const [path] = location.hash.replace(/^#\/?/, '').split('?');
  const query = new URLSearchParams({ model: state.model });
  if (state.runId !== 'default') query.set('run', state.runId);
  const next = `#/${path || 'overview'}?${query}`;
  if (location.hash !== next) history.replaceState(null, '', next);
}

export function navigate(hash) {
  if (location.hash === hash) render();
  else location.hash = hash;
}

function setModel(model) {
  if (!state.index?.models.includes(model)) return;
  state.model = model;
  storage.set('model', model);
  $('model-select').value = model;
  render();
}

function renderToolbar() {
  const runSelect = $('run-select');
  const complete = state.runs.filter((run) => run.status === 'complete');
  runSelect.innerHTML = complete.map((run) => html`<option value="${run.id}">${run.name}${run.signal_date ? ` · ${date(run.signal_date)}` : ''}</option>`).join('');
  runSelect.value = state.runId;
  const modelSelect = $('model-select');
  modelSelect.innerHTML = state.index
    ? state.index.models.map((model) => html`<option value="${model}">${state.index.labels[model]}</option>`).join('')
    : '';
  modelSelect.disabled = !state.index;
  if (state.model) modelSelect.value = state.model;
}

function renderContext() {
  const bar = $('context-bar');
  if (!state.index) { bar.innerHTML = ''; return; }
  const { ws } = state.index;
  const summary = state.index.summaries[state.model];
  bar.innerHTML = html`
    <span>Signal as of <b>${date(ws.signal_date)}</b></span><span class="sep"></span>
    <span><b>${ws.dataset}</b></span><span class="sep"></span>
    <span><b>${int(ws.quality.accepted_tickers)}</b> securities · <b>${int(summary?.folds)}</b> monthly out-of-sample folds</span><span class="sep"></span>
    <span>${ws.config.horizon_sessions}-session horizon · ${ws.config.embargo_sessions}-session embargo · ${ws.config.transaction_cost_bps} bps costs${ws.config.max_per_sector ? ` · ≤${ws.config.max_per_sector} names per sector` : ''}${ws.config.rebalance_every_folds > 1 ? ` · rebalanced ${cadence(ws.config.rebalance_every_folds)}` : ''}${ws.config.hold_buffer ? ` · holdings kept while in top ${ws.config.hold_buffer}` : ''}${ws.config.neutralize_volatility ? ' · volatility-neutral scores' : ''}</span>`;
  const unavailable = ws.quality.unavailable_tickers || [];
  if (unavailable.length) {
    bar.insertAdjacentHTML('beforeend', html`<span class="sep"></span><span class="neg" title="Yahoo Finance returned no prices for: ${unavailable.join(', ')}">${unavailable.length} ticker${unavailable.length === 1 ? '' : 's'} unavailable</span>`);
  }
}

let renderToken = 0;
async function render() {
  hideTooltip();
  const token = ++renderToken;
  const route = parseRoute();
  const view = VIEWS[route.view];
  document.querySelectorAll('#nav a').forEach((link) => {
    if (link.dataset.view === route.view) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  });
  closeMenu();
  const container = $('view');
  const ctx = {
    el: container,
    index: state.index,
    model: state.model,
    params: route.params,
    runId: state.runId,
    runs: state.runs,
    catalog: state.catalog,
    navigate,
    setModel,
    toast,
    openRun,
    submitRun,
  };
  $('view-title').textContent = view.title;
  $('view-subtitle').textContent = state.index || !view.needsWorkspace ? (view.subtitle?.(ctx) || '') : '';
  document.title = `${view.title} · AlphaCast`;
  if (view.needsWorkspace !== false && !state.index) {
    container.innerHTML = state.record?.status === 'failed'
      ? html`<div class="loading"><p>This workspace failed: ${state.record.error}</p><a class="button" href="#/runs">Open runs</a></div>`
      : `<div class="skeleton-view" aria-busy="true" aria-label="Loading workspace">
          <div class="skeleton-kpis">${'<div class="skeleton"></div>'.repeat(6)}</div>
          <div class="skeleton skeleton-bar"></div>
          <div class="skeleton-grid"><div class="skeleton skeleton-panel"></div><div class="skeleton skeleton-panel"></div></div>
          <p class="sr-only">Loading workspace…</p>
        </div>`;
    return;
  }
  try {
    await view.render(ctx);
    syncAddress();
  } catch (error) {
    if (token !== renderToken) return;
    console.error(error);
    container.innerHTML = html`<div class="loading"><p>Something went wrong rendering this view.</p><p class="muted">${error.message}</p></div>`;
  }
}

async function openRun(runId, { quiet = false } = {}) {
  try {
    const record = await api.run(runId);
    if (record.status !== 'complete') {
      if (!quiet) toast(record.status === 'failed' ? `Run failed: ${record.error}` : 'That run is still in progress.');
      return false;
    }
    state.runId = runId;
    state.record = record;
    state.index = workspaceIndex(record.workspace);
    storage.set('run', runId);
    if (!state.index.models.includes(state.model)) state.model = leadingModel(state.index);
    renderToolbar();
    renderContext();
    render();
    return true;
  } catch (error) {
    if (runId !== 'default') {
      if (!quiet) toast(`${error.message} Showing the default workspace.`);
      return openRun('default', { quiet: true });
    }
    state.record = { status: 'failed', error: error.message };
    render();
    return false;
  }
}

async function refreshRuns() {
  try {
    state.runs = await api.runs();
  } catch (error) {
    toast(`Could not reach the server: ${error.message}`);
    return;
  }
  const listed = new Set(state.runs.map((run) => run.id));
  for (const id of [...state.watching]) {
    if (!listed.has(id)) {
      state.watching.delete(id);
      toast('The server restarted and that run was lost. Runs live in memory, so start it again.', 8000);
    }
  }
  for (const run of state.runs) {
    if (state.watching.has(run.id) && run.status !== 'queued' && run.status !== 'running') {
      state.watching.delete(run.id);
      if (run.status === 'complete') {
        toast(`“${run.name}” finished. Opening it now.`);
        await openRun(run.id);
      } else {
        toast(`“${run.name}” failed: ${run.error}`, 8000);
      }
    }
  }
  renderToolbar();
  const active = state.runs.some((run) => run.status === 'queued' || run.status === 'running');
  clearTimeout(state.pollTimer);
  if (active) state.pollTimer = setTimeout(refreshRuns, 1500);
  if (parseRoute().view === 'runs') runs.refresh?.({ runs: state.runs, openRun, runId: state.runId });
}

async function submitRun(payload) {
  const record = await api.createRun(payload);
  state.watching.add(record.id);
  toast(`Queued “${record.name}”. You can keep working while it runs.`);
  await refreshRuns();
  return record;
}

function closeMenu() {
  $('sidebar').classList.remove('open');
  $('scrim').hidden = true;
  $('menu-button').setAttribute('aria-expanded', 'false');
}

function syncThemeButton() {
  const label = document.documentElement.dataset.theme === 'light' ? 'Switch to dark theme' : 'Switch to light theme';
  $('theme-button').setAttribute('aria-label', label);
  $('theme-button').title = label;
}

function bindGlossary() {
  const show = (element, event) => {
    const [title, text] = DEFINITIONS[element.dataset.term] || [];
    if (!title) return;
    const box = element.getBoundingClientRect();
    const anchor = event?.clientX ? event : { clientX: box.left, clientY: box.bottom + 4 };
    showTooltip(anchor, `${tooltipHtml(title, [])}<div class="tt-text">${text}</div>`);
  };
  document.addEventListener('pointerover', (event) => { const el = event.target.closest?.('[data-term]'); if (el) show(el, event); });
  document.addEventListener('pointerout', (event) => { if (event.target.closest?.('[data-term]')) hideTooltip(); });
  document.addEventListener('focusin', (event) => { const el = event.target.closest?.('[data-term]'); if (el) show(el); });
  document.addEventListener('focusout', (event) => { if (event.target.closest?.('[data-term]')) hideTooltip(); });
}

function bindShell() {
  syncThemeButton();
  bindGlossary();
  const palette = initPalette(() => ({ index: state.index, navigate, setModel }));
  initShortcutHelp();
  $('search-button').addEventListener('click', () => palette.open());
  if (!/Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent)) $('search-button').querySelector('kbd').textContent = 'Ctrl K';
  window.addEventListener('hashchange', render);
  $('run-select').addEventListener('change', (event) => openRun(event.target.value));
  $('model-select').addEventListener('change', (event) => setModel(event.target.value));
  $('theme-button').addEventListener('click', () => {
    const next = document.documentElement.dataset.theme === 'light' ? 'dark' : 'light';
    document.documentElement.dataset.theme = next;
    storage.set('theme', next);
    syncThemeButton();
    render();
  });
  $('menu-button').addEventListener('click', () => {
    const open = !$('sidebar').classList.contains('open');
    $('sidebar').classList.toggle('open', open);
    $('scrim').hidden = !open;
    $('menu-button').setAttribute('aria-expanded', String(open));
  });
  $('scrim').addEventListener('click', closeMenu);
  document.addEventListener('keydown', (event) => { if (event.key === 'Escape') closeMenu(); });
  let width = window.innerWidth;
  let resizeTimer;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      if (Math.abs(window.innerWidth - width) > 24) { width = window.innerWidth; render(); }
    }, 180);
  });
}

async function boot() {
  const { query } = parseRoute();
  if (query.run) state.runId = query.run;
  if (query.model) state.model = query.model;
  bindShell();
  render();
  try {
    [state.catalog] = await Promise.all([api.catalog(), refreshRuns()]);
  } catch (error) {
    toast(`Could not load the catalog: ${error.message}`);
  }
  const known = state.runs.find((run) => run.id === state.runId && run.status === 'complete');
  await openRun(known ? state.runId : 'default', { quiet: true });
}

boot();

