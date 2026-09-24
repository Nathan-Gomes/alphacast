// Small render helpers shared across views. Each returns an HTML string.

import { escapeHtml, isNum } from '../format.js';

export function tickerLink(ticker) {
  const safe = escapeHtml(ticker);
  return `<a class="ticker ticker-link" href="#/security/${encodeURIComponent(ticker)}">${safe}</a>`;
}

export function pctBar(percentile) {
  if (!isNum(percentile)) return '—';
  return `<span class="pct-bar"><i><b style="width:${Math.max(2, percentile)}%"></b></i><span>${percentile.toFixed(0)}</span></span>`;
}

export function rankChange(change) {
  if (!isNum(change)) return '<span class="tag new" title="Not ranked at the last rebalance">new</span>';
  if (change === 0) return '<span class="muted">0</span>';
  return `<span class="${change > 0 ? 'pos' : 'neg'}">${change > 0 ? '▲' : '▼'} ${Math.abs(change)}</span>`;
}

const STATUS_LABELS = {
  healthy: 'Healthy', watch: 'Watch', degraded: 'Degraded',
  stable: 'Stable', moderate: 'Moderate', shifted: 'Shifted',
  complete: 'Complete', running: 'Running', queued: 'Queued', failed: 'Failed',
};

export function statusBadge(status) {
  return `<span class="badge ${escapeHtml(status)}">${escapeHtml(STATUS_LABELS[status] || status)}</span>`;
}

/** Percentile cell tinted on a one-hue sequential ramp. */
export function heatCell(percentile) {
  if (!isNum(percentile)) return '—';
  const step = percentile >= 80 ? 3 : percentile >= 60 ? 2 : percentile >= 40 ? 1 : 0;
  return `<span class="heat s${step}">${percentile.toFixed(0)}</span>`;
}

export function panel({ title, note = '', body = '', actions = '', id = '', flush = false }) {
  return `<section class="panel"${id ? ` id="${id}"` : ''}>
    <div class="panel-head"><div><h2>${escapeHtml(title)}</h2>${note ? `<p>${note}</p>` : ''}</div>${actions ? `<div class="actions">${actions}</div>` : ''}</div>
    <div class="panel-body${flush ? ' flush table-wrap' : ''}">${body}</div>
  </section>`;
}

/** "3/5" with dots, so agreement reads at a glance. */
export function consensusCell(count, total) {
  const dots = Array.from({ length: total }, (_, i) => `<i class="${i < count ? 'on' : ''}"></i>`).join('');
  return `<span class="consensus" title="${count} of ${total} models rank it in the top quintile"><span class="dots" aria-hidden="true">${dots}</span>${count}/${total}</span>`;
}
