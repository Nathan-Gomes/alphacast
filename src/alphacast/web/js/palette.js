// Command palette: ⌘K / Ctrl+K or "/" opens a search over views, models and securities.

import { escapeHtml } from './format.js';

const VIEWS = [
  ['overview', 'Overview', 'Current signal and model health'],
  ['screener', 'Screener', 'Every security, ranked'],
  ['portfolio', 'Portfolio', 'Holdings, entries and exits, tilts'],
  ['backtest', 'Backtest', 'Growth, drawdowns, cost sensitivity'],
  ['models', 'Models', 'Compare all models'],
  ['diagnostics', 'Diagnostics', 'IC, quintiles, sectors, regimes'],
  ['monitoring', 'Monitoring', 'Health, reliance and feature drift'],
  ['runs', 'Runs', 'Start a new study'],
];

let dialog = null;

function build() {
  dialog = document.createElement('dialog');
  dialog.className = 'palette';
  dialog.setAttribute('aria-label', 'Go to');
  dialog.innerHTML = `
    <input type="text" role="combobox" aria-expanded="true" aria-controls="palette-list" aria-autocomplete="list"
      placeholder="Jump to a ticker, view or model…" autocomplete="off" spellcheck="false">
    <ul id="palette-list" role="listbox"></ul>
    <p class="palette-hint"><kbd>↑</kbd><kbd>↓</kbd> move · <kbd>Enter</kbd> open · <kbd>Esc</kbd> close</p>`;
  document.body.append(dialog);
  dialog.addEventListener('click', (event) => { if (event.target === dialog) dialog.close(); });
  return dialog;
}

/** getContext() returns { index, navigate, setModel } at the moment the palette opens. */
export function initPalette(getContext) {
  let items = [];
  let active = 0;

  function entries(query) {
    const { index } = getContext();
    const q = query.trim().toLowerCase();
    const views = VIEWS.map(([id, label, detail]) => ({ kind: 'View', label, detail, run: (ctx) => ctx.navigate(`#/${id}`) }));
    const models = index ? index.models.map((id) => ({
      kind: 'Model', label: index.labels[id], detail: 'Make active', run: (ctx) => ctx.setModel(id),
    })) : [];
    const securities = index ? index.tickers.map((ticker) => ({
      kind: 'Security', label: ticker, detail: index.profiles[ticker].sector, run: (ctx) => ctx.navigate(`#/security/${ticker}`),
    })) : [];
    if (!q) return [...views, ...models];
    const score = (item) => {
      const label = item.label.toLowerCase();
      if (label === q) return 0;
      if (label.startsWith(q)) return 1;
      if (label.includes(q)) return 2;
      if (item.detail.toLowerCase().includes(q)) return 3;
      return 9;
    };
    return [...securities, ...views, ...models]
      .map((item) => ({ item, rank: score(item) }))
      .filter(({ rank }) => rank < 9)
      .sort((a, b) => a.rank - b.rank)
      .slice(0, 12)
      .map(({ item }) => item);
  }

  function paint() {
    const list = dialog.querySelector('ul');
    list.innerHTML = items.length
      ? items.map((item, i) => `<li role="option" id="palette-${i}" aria-selected="${i === active}" data-index="${i}">
          <span class="palette-kind">${escapeHtml(item.kind)}</span><strong>${escapeHtml(item.label)}</strong><span class="palette-detail">${escapeHtml(item.detail)}</span></li>`).join('')
      : '<li class="palette-empty">No matches</li>';
    dialog.querySelector('input').setAttribute('aria-activedescendant', items.length ? `palette-${active}` : '');
    list.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: 'nearest' });
  }

  function choose(i) {
    const item = items[i];
    if (!item) return;
    dialog.close();
    item.run(getContext());
  }

  function open() {
    if (!dialog) {
      build();
      const input = dialog.querySelector('input');
      input.addEventListener('input', () => { items = entries(input.value); active = 0; paint(); });
      input.addEventListener('keydown', (event) => {
        if (event.key === 'ArrowDown') { active = Math.min(active + 1, items.length - 1); paint(); event.preventDefault(); }
        if (event.key === 'ArrowUp') { active = Math.max(active - 1, 0); paint(); event.preventDefault(); }
        if (event.key === 'Enter') { choose(active); event.preventDefault(); }
      });
      dialog.querySelector('ul').addEventListener('click', (event) => {
        const li = event.target.closest('li[data-index]');
        if (li) choose(Number(li.dataset.index));
      });
    }
    const input = dialog.querySelector('input');
    input.value = '';
    items = entries('');
    active = 0;
    paint();
    dialog.showModal();
    input.focus();
  }

  document.addEventListener('keydown', (event) => {
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName) || document.activeElement?.isContentEditable;
    if ((event.key === 'k' && (event.metaKey || event.ctrlKey)) || (event.key === '/' && !typing)) {
      event.preventDefault();
      if (dialog?.open) dialog.close(); else open();
    }
  });
  return { open };
}

const SHORTCUTS = [
  ['⌘K or /', 'Search tickers, views and models (Ctrl K on Windows)'],
  ['?', 'Show this list'],
  ['← →', 'Step through a focused chart (Shift for ten)'],
  ['Home  End', 'Jump to the ends of a focused chart'],
  ['Enter', 'Open the focused table row'],
  ['Esc', 'Close dialogs and the menu'],
];

let help = null;

/** "?" opens a list of keyboard shortcuts. */
export function initShortcutHelp() {
  document.addEventListener('keydown', (event) => {
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName);
    if (event.key !== '?' || typing || event.metaKey || event.ctrlKey) return;
    event.preventDefault();
    if (!help) {
      help = document.createElement('dialog');
      help.className = 'palette shortcuts';
      help.setAttribute('aria-labelledby', 'shortcuts-title');
      help.innerHTML = `<h2 id="shortcuts-title">Keyboard shortcuts</h2><dl>${SHORTCUTS.map(([keys, what]) => `<div><dt><kbd>${escapeHtml(keys)}</kbd></dt><dd>${escapeHtml(what)}</dd></div>`).join('')}</dl><p class="palette-hint"><kbd>Esc</kbd> close</p>`;
      help.addEventListener('click', (e) => { if (e.target === help) help.close(); });
      document.body.append(help);
    }
    if (help.open) help.close(); else help.showModal();
  });
}
