import { api } from '../api.js';
import { date, escapeHtml, html, raw } from '../format.js';
import { statusBadge } from './parts.js';

const today = () => new Date().toISOString().slice(0, 10);
const RUN_ESTIMATE = 'Frozen-snapshot runs of all five models take one to three minutes; tree models are the slow part.';

function historyHtml(runs, activeId) {
  if (!runs.length) return '<p class="empty">No runs yet.</p>';
  return `<table><thead><tr><th scope="col">Run</th><th scope="col">Status</th><th scope="col">Dataset</th><th scope="col">Signal</th><th scope="col"></th></tr></thead><tbody>${runs.map((run) => {
    const running = run.status === 'running' || run.status === 'queued';
    const progress = running ? `<div class="progress" aria-label="Progress ${Math.round(run.progress * 100)}%"><b style="width:${Math.round(run.progress * 100)}%"></b></div><div class="muted" style="font-size:11.5px;margin-top:3px;white-space:normal">${escapeHtml(run.message)}</div>` : '';
    const error = run.status === 'failed' ? `<div class="neg" style="font-size:12px;white-space:normal;max-width:320px">${escapeHtml(run.error)}</div>` : '';
    const actions = run.status === 'complete'
      ? `${run.id === activeId ? '<span class="tag">Active</span>' : `<button class="button small" type="button" data-open="${escapeHtml(run.id)}">Open</button>`} <a class="button small" href="${api.exportUrl(run.id)}" download>JSON</a>`
      : '';
    const models = (run.request?.models || []).length;
    return `<tr><td><strong>${escapeHtml(run.name)}</strong><div class="muted" style="font-size:12px">${escapeHtml(run.request?.source || '')} · ${models} model${models === 1 ? '' : 's'} · top ${escapeHtml(run.request?.top_n ?? '')} · ${escapeHtml(run.request?.transaction_cost_bps ?? '')} bps</div></td>
      <td style="min-width:150px">${statusBadge(run.status)}${progress}${error}</td>
      <td class="muted" style="white-space:normal">${escapeHtml(run.dataset || '—')}</td>
      <td>${run.signal_date ? date(run.signal_date) : '—'}</td>
      <td class="num">${actions}</td></tr>`;
  }).join('')}</tbody></table>`;
}

let mounted = null;

export default {
  title: 'Runs',
  needsWorkspace: false,
  subtitle: () => 'Configure a study, run it in the background, and switch workspaces',
  refresh({ runs, openRun, runId }) {
    const target = document.getElementById('run-history');
    if (!target || !mounted) return;
    target.innerHTML = historyHtml(runs, runId);
    target.querySelectorAll('[data-open]').forEach((button) => button.addEventListener('click', () => openRun(button.dataset.open)));
  },
  render(ctx) {
    const catalog = ctx.catalog;
    if (!catalog) {
      ctx.el.innerHTML = '<div class="loading"><div class="spinner"></div><p>Loading options…</p></div>';
      return;
    }
    mounted = true;
    const universeTickers = Object.fromEntries(catalog.universes.map((universe) => [universe.id, universe.tickers]));
    ctx.el.innerHTML = html`
      <div class="grid cols-main">
        <section class="panel">
          <div class="panel-head"><div><h2>New research run</h2><p>Every model runs on the same expanding, embargoed monthly folds. ${RUN_ESTIMATE}</p></div></div>
          <form class="panel-body" id="run-form" novalidate>
            <div class="form-grid">
              <label class="field full">Run name <input type="text" name="name" maxlength="60" placeholder="e.g. Starter 30, 25 bps costs"></label>
              <fieldset class="field full" style="border:0;padding:0;margin:0"><legend style="margin-bottom:6px">Data source</legend>
                <div class="choice-list">${catalog.sources.map((source, i) => raw(html`<label class="choice"><input type="radio" name="source" value="${source.id}" ${raw(i === 0 ? 'checked' : '')}><span><strong>${source.label}</strong><small>${source.detail}</small></span></label>`))}</div>
              </fieldset>
              <fieldset class="field full" id="universe-field" style="border:0;padding:0;margin:0"><legend style="margin-bottom:6px">Universe</legend>
                <div class="choice-list">
                  ${catalog.universes.map((universe, i) => raw(html`<label class="choice"><input type="radio" name="universe" value="${universe.id}" ${raw(i === 0 ? 'checked' : '')}><span><strong>${universe.label}</strong><small>${universe.description}</small></span></label>`))}
                  <label class="choice" id="custom-choice"><input type="radio" name="universe" value="custom"><span><strong>Custom tickers</strong><small>Yahoo Finance only. 10 to 150 symbols; sectors resolve from Yahoo metadata when unknown.</small></span></label>
                </div>
              </fieldset>
              <label class="field full" id="tickers-field" hidden>Tickers <textarea name="tickers" rows="3" spellcheck="false" placeholder="AAPL, MSFT, NVDA, …"></textarea></label>
              <label class="field">Start date <input type="date" name="start" value="${catalog.defaults.start}" min="2000-01-01"></label>
              <label class="field">End date <input type="date" name="end" value="${today()}"></label>
              <fieldset class="field full" style="border:0;padding:0;margin:0"><legend style="margin-bottom:6px">Models</legend>
                <div class="model-checks">${catalog.models.map((model) => raw(html`<label class="check"><input type="checkbox" name="models" value="${model.id}" checked> ${model.label}</label>`))}</div>
              </fieldset>
              <label class="field">Portfolio size (top N) <input type="number" name="top_n" min="3" max="40" value="${catalog.defaults.top_n}"></label>
              <label class="field">One-way cost (bps) <input type="number" name="transaction_cost_bps" min="0" max="250" step="1" value="${catalog.defaults.transaction_cost_bps}"></label>
            </div>
            <p class="form-error" id="form-error" role="alert"></p>
            <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap"><button class="button primary" type="submit" id="submit">Run study</button><span class="muted" style="font-size:12.5px">Runs live in server memory and reset when the service restarts. Export anything you want to keep.</span></div>
          </form>
        </section>
        <section class="panel">
          <div class="panel-head"><div><h2>Run history</h2><p>The default workspace is precomputed from the frozen snapshot.</p></div></div>
          <div class="panel-body flush table-wrap" id="run-history"></div>
        </section>
      </div>`;

    const form = document.getElementById('run-form');
    const error = document.getElementById('form-error');
    const sync = () => {
      const source = form.source.value;
      const universeField = document.getElementById('universe-field');
      universeField.hidden = source === 'synthetic';
      const custom = document.getElementById('custom-choice');
      custom.hidden = source !== 'yahoo';
      if (source !== 'yahoo' && form.universe.value === 'custom') form.universe.value = 'us_large_cap';
      document.getElementById('tickers-field').hidden = !(source === 'yahoo' && form.universe.value === 'custom');
    };
    form.addEventListener('change', sync);
    sync();
    this.refresh({ runs: ctx.runs, openRun: ctx.openRun, runId: ctx.runId });

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      error.textContent = '';
      const data = new FormData(form);
      const models = data.getAll('models');
      const payload = {
        name: data.get('name') || '',
        source: data.get('source'),
        universe: data.get('source') === 'synthetic' ? 'us_large_cap' : data.get('universe'),
        tickers: String(data.get('tickers') || '').split(/[\s,;]+/).map((ticker) => ticker.trim().toUpperCase()).filter(Boolean),
        start: data.get('start'),
        end: data.get('end'),
        models,
        top_n: Number(data.get('top_n')),
        transaction_cost_bps: Number(data.get('transaction_cost_bps')),
      };
      if (!models.length) { error.textContent = 'Select at least one model.'; return; }
      if (payload.universe === 'custom' && payload.tickers.length < 10) { error.textContent = `Enter at least ten tickers (${payload.tickers.length} so far).`; return; }
      if (payload.start >= payload.end) { error.textContent = 'The start date must be before the end date.'; return; }
      if (payload.source !== 'yahoo' && payload.universe !== 'custom') {
        payload.tickers = universeTickers[payload.universe] || [];
      }
      const button = document.getElementById('submit');
      button.disabled = true;
      try {
        await ctx.submitRun(payload);
        form.name.value = '';
      } catch (failure) {
        error.textContent = failure.message;
      } finally {
        button.disabled = false;
      }
    });
  },
};
