// Sortable, keyboard-accessible data table.

import { escapeHtml, isNum } from './format.js';

/**
 * columns: [{ key, label, num?, render?(row) -> html, sort?(row) -> value, title? }]
 * Returns an object with update(rows) so filters can re-render without losing sort.
 */
export function dataTable(container, {
  columns, rows, sortKey = null, sortDir = 'desc', onRowClick = null, rowClass = null,
  empty = 'No rows match.', caption = '', afterRender = null,
}) {
  const state = { rows, sortKey, sortDir };

  const valueOf = (row, column) => (column.sort ? column.sort(row) : row[column.key]);

  function sorted() {
    const column = columns.find((item) => item.key === state.sortKey);
    if (!column) return state.rows;
    const direction = state.sortDir === 'asc' ? 1 : -1;
    return [...state.rows].sort((left, right) => {
      const a = valueOf(left, column);
      const b = valueOf(right, column);
      const aMissing = a === null || a === undefined || (typeof a === 'number' && !isNum(a));
      const bMissing = b === null || b === undefined || (typeof b === 'number' && !isNum(b));
      if (aMissing || bMissing) return aMissing - bMissing;
      return (typeof a === 'string' ? a.localeCompare(b) : a - b) * direction;
    });
  }

  function render() {
    const body = sorted();
    const head = columns.map((column) => {
      const active = column.key === state.sortKey;
      const sortAttr = active ? ` aria-sort="${state.sortDir === 'asc' ? 'ascending' : 'descending'}"` : '';
      const label = column.sortable === false
        ? escapeHtml(column.label)
        : `<button type="button" data-sort="${escapeHtml(column.key)}">${escapeHtml(column.label)}</button>`;
      return `<th scope="col" class="${column.num ? 'num' : ''}"${sortAttr}${column.title ? ` title="${escapeHtml(column.title)}"` : ''}>${label}</th>`;
    }).join('');
    const rowsHtml = body.length ? body.map((row, index) => {
      const extra = rowClass ? rowClass(row) : '';
      const interactive = onRowClick ? ' clickable" tabindex="0' : '';
      return `<tr data-index="${index}" class="${extra}${interactive}">${columns.map((column) => `<td class="${column.num ? 'num' : ''}">${column.render ? column.render(row) : escapeHtml(row[column.key])}</td>`).join('')}</tr>`;
    }).join('') : `<tr><td class="empty" colspan="${columns.length}">${escapeHtml(empty)}</td></tr>`;
    container.innerHTML = `<table>${caption ? `<caption class="sr-only">${escapeHtml(caption)}</caption>` : ''}<thead><tr>${head}</tr></thead><tbody>${rowsHtml}</tbody></table>`;

    container.querySelectorAll('th button').forEach((button) => button.addEventListener('click', () => {
      const key = button.dataset.sort;
      if (state.sortKey === key) state.sortDir = state.sortDir === 'asc' ? 'desc' : 'asc';
      else {
        state.sortKey = key;
        const column = columns.find((item) => item.key === key);
        state.sortDir = column.num ? 'desc' : 'asc';
      }
      render();
      container.querySelector(`th button[data-sort="${CSS.escape(key)}"]`)?.focus();
    }));
    if (onRowClick) {
      container.querySelectorAll('tbody tr.clickable').forEach((tr) => {
        const row = body[Number(tr.dataset.index)];
        tr.addEventListener('click', (event) => { if (!event.target.closest('a,button')) onRowClick(row); });
        tr.addEventListener('keydown', (event) => { if (event.key === 'Enter' && event.target === tr) onRowClick(row); });
      });
    }
    if (afterRender) afterRender(container);
  }

  render();
  return {
    update(nextRows) { state.rows = nextRows; render(); },
    rows: () => sorted(),
  };
}
