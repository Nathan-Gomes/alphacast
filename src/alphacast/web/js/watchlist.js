// A per-browser watchlist of tickers. It is a convenience, so storage failures are
// ignored and the list simply starts empty.

const KEY = 'alphacast.watchlist';

function read() {
  try { return new Set(JSON.parse(localStorage.getItem(KEY) || '[]')); } catch { return new Set(); }
}

export const watchlist = {
  has: (ticker) => read().has(ticker),
  all: () => [...read()],
  toggle(ticker) {
    const set = read();
    if (set.has(ticker)) set.delete(ticker); else set.add(ticker);
    try { localStorage.setItem(KEY, JSON.stringify([...set])); } catch { /* private mode */ }
    return set.has(ticker);
  },
};

export function starButton(ticker) {
  const on = watchlist.has(ticker);
  return `<button type="button" class="star${on ? ' on' : ''}" data-star="${ticker}" aria-pressed="${on}" aria-label="${on ? 'Remove' : 'Add'} ${ticker} ${on ? 'from' : 'to'} watchlist" title="${on ? 'Remove from' : 'Add to'} watchlist"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 3 2.7 5.6 6.1.8-4.5 4.2 1.1 6.1L12 16.8 6.6 19.7l1.1-6.1-4.5-4.2 6.1-.8z"/></svg></button>`;
}

/** Wire every star inside a container; onChange runs after a toggle. */
export function bindStars(container, onChange = () => {}) {
  container.querySelectorAll('[data-star]').forEach((button) => {
    button.addEventListener('click', (event) => {
      event.stopPropagation();
      const on = watchlist.toggle(button.dataset.star);
      button.classList.toggle('on', on);
      button.setAttribute('aria-pressed', String(on));
      button.setAttribute('aria-label', `${on ? 'Remove' : 'Add'} ${button.dataset.star} ${on ? 'from' : 'to'} watchlist`);
      onChange(button.dataset.star, on);
    });
  });
}
