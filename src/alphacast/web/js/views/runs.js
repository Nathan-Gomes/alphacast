import { api } from '../api.js';
import { cadence, date, escapeHtml, html, raw } from '../format.js';
import { statusBadge } from './parts.js';

const today = () => new Date().toISOString().slice(0, 10);

function duration(seconds) {
  if (seconds < 90) return `${Math.max(5, Math.round(seconds / 5) * 5)} seconds`;
  const minutes = Math.round(seconds / 60);
  return `${minutes} minute${minutes === 1 ? '' : 's'}`;
}

function historyHtml(runs, activeId) {
  if (!runs.length) return '<p class="empty">No runs yet.</p>';
  return `<table><thead><tr><th scope="col">Run</th><th scope="col">Status</th><th scope="col"></th></tr></thead><tbody>${runs.map((run) => {
    const running = run.status === 'running' || run.status === 'queued';
    const progress = running ? `<div class="progress" aria-label="Progress ${Math.round(run.progress * 100)}%"><b style="width:${Math.round(run.progress * 100)}%"></b></div><div class="muted" style="font-size:11.5px;margin-top:3px;white-space:normal">${escapeHtml(run.message)}</div>` : '';
    const error = run.status === 'failed' ? `<div class="neg" style="font-size:12px;white-space:normal;max-width:320px">${escapeHtml(run.error)}</div>` : '';
    const actions = run.status === 'complete'
      ? `${run.id === activeId ? '<span class="tag">Active</span>' : `<button class="button small" type="button" data-open="${escapeHtml(run.id)}">Open</button>`} <a class="button small" href="${api.exportUrl(run.id)}" download>JSON</a>`
      : '';
    const models = (run.request?.models || []).length;
    return `<tr><td><strong>${escapeHtml(run.name)}</strong><div class="muted" style="font-size:12px;white-space:normal">${escapeHtml(run.dataset || run.request?.source || '')}${run.signal_date ? ` · signal ${date(run.signal_date)}` : ''}</div><div class="muted" style="font-size:12px">${models} model${models === 1 ? '' : 's'} · top ${escapeHtml(run.request?.top_n ?? '')}${run.request?.max_per_sector ? ` (≤${escapeHtml(run.request.max_per_sector)}/sector)` : ''}${run.request?.rebalance_every_folds > 1 ? ` · ${cadence(run.request.rebalance_every_folds)}` : ''}${run.request?.hold_buffer ? ` · buffer ${escapeHtml(run.request.hold_buffer)}` : ''} · ${escapeHtml(run.request?.transaction_cost_bps ?? '')} bps</div></td>
      <td style="min-width:150px">${statusBadge(run.status)}${progress}${error}</td>
      <td><div class="run-actions">${actions}</div></td></tr>`;
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
          <div class="panel-head"><div><h2>New research run</h2><p>Every model runs on the same expanding, embargoed monthly folds, one run at a time.</p></div></div>
          <form class="panel-body" id="run-form" novalidate>
            <div class="form-grid">
              <label class="field full">Run name <input type="text" name="name" maxlength="60" placeholder="e.g. Starter 30, 25 bps costs"></label>
              <fieldset class="field full fieldset-plain"><legend>Data source</legend>
                <div class="choice-list">${catalog.sources.map((source, i) => raw(html`<label class="choice"><input type="radio" name="source" value="${source.id}" ${raw(i === 0 ? 'checked' : '')}><span><strong>${source.label}</strong><small>${source.detail}</small></span></label>`))}</div>
              </fieldset>
              <fieldset class="field full fieldset-plain" id="universe-field"><legend>Universe</legend>
                <div class="choice-list">
                  ${catalog.universes.map((universe, i) => raw(html`<label class="choice"><input type="radio" name="universe" value="${universe.id}" ${raw(i === 0 ? 'checked' : '')}><span><strong>${universe.label}</strong><small>${universe.description}</small></span></label>`))}
                  <label class="choice" id="custom-choice"><input type="radio" name="universe" value="custom"><span><strong>Custom tickers</strong><small>Yahoo Finance only. 10 to 150 symbols; sectors resolve from Yahoo metadata when unknown.</small></span></label>
                </div>
              </fieldset>
              <label class="field full" id="tickers-field" hidden>Tickers <textarea name="tickers" rows="3" spellcheck="false" placeholder="AAPL, MSFT, NVDA, …"></textarea></label>
              <label class="field">Start date <input type="date" name="start" value="${catalog.defaults.start}" min="2000-01-01"></label>
              <label class="field">End date <input type="date" name="end" value="${today()}"></label>
              <fieldset class="field full fieldset-plain"><legend>Models</legend>
                <div class="model-checks">${catalog.models.map((model) => raw(html`<label class="check" title="About ${duration(model.seconds)} on this server"><input type="checkbox" name="models" value="${model.id}" ${raw(model.default ? 'checked' : '')}> ${model.label}${raw(model.seconds >= 60 ? ' <span class="tag">slower</span>' : '')}</label>`))}</div>
              </fieldset>
              <label class="field">Portfolio size (top N) <input type="number" name="top_n" min="3" max="40" value="${catalog.defaults.top_n}"></label>
              <label class="field">Max names per sector <select name="max_per_sector"><option value="">No cap</option>${[2, 3, 4, 5].map((cap) => raw(`<option value="${cap}">${cap}</option>`))}</select></label>
              <label class="field">Rebalance <select name="rebalance_every_folds"><option value="1">Monthly</option><option value="2">Every two months</option><option value="3">Quarterly</option></select></label>
              <label class="field">Holding buffer <select name="hold_buffer"><option value="">None: trade to the top N</option><option value="1.5">Keep while in top 1.5 × N</option><option value="2">Keep while in top 2 × N</option></select></label>
              <label class="field">One-way cost (bps) <input type="number" name="transaction_cost_bps" min="0" max="250" step="1" value="${catalog.defaults.transaction_cost_bps}"></label>
            </div>
            <p class="form-error" id="form-error" role="alert"></p>
            <div class="form-actions"><button class="button primary" type="submit" id="submit">Run study</button><span class="muted" id="estimate" aria-live="polite"></span></div>
            <p class="note">Runs live in server memory and reset when the service restarts. Export anything you want to keep.</p>
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
      const chosen = new Set(new FormData(form).getAll('models'));
      const seconds = catalog.overhead_seconds + catalog.models.filter((model) => chosen.has(model.id)).reduce((sum, model) => sum + model.seconds, 0)
        + (source === 'yahoo' ? 20 : 0);
      const waiting = ctx.runs.filter((run) => run.status === 'queued' || run.status === 'running').length;
      document.getElementById('estimate').textContent = chosen.size
        ? `Estimated ${duration(seconds)}${source === 'yahoo' ? ' plus download time' : ''}${waiting ? ` after ${waiting} run${waiting === 1 ? '' : 's'} ahead in the queue` : ''}.`
        : '';
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
        max_per_sector: data.get('max_per_sector') ? Number(data.get('max_per_sector')) : null,
        rebalance_every_folds: Number(data.get('rebalance_every_folds') || 1),
        hold_buffer: data.get('hold_buffer') ? Math.round(Number(data.get('top_n')) * Number(data.get('hold_buffer'))) : null,
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
        form.elements.namedItem('name').value = '';
      } catch (failure) {
        error.textContent = failure.message;
      } finally {
        button.disabled = false;
      }
    });
  },
};
