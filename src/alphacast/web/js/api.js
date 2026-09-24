// Thin client for the AlphaCast API. Every error surfaces the server's message.

async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  let body = null;
  try { body = await response.json(); } catch { /* non-JSON error page */ }
  if (!response.ok) {
    const detail = body?.detail;
    const message = Array.isArray(detail)
      ? detail.map((item) => item.msg?.replace(/^Value error, /, '')).join(' ')
      : detail || `Request failed (${response.status}).`;
    throw new Error(message);
  }
  return body;
}

const securityCache = new Map();

export const api = {
  catalog: () => request('/api/catalog'),
  runs: () => request('/api/runs').then((body) => body.runs),
  run: (id) => request(`/api/runs/${encodeURIComponent(id)}`),
  createRun: (payload) => request('/api/runs', { method: 'POST', body: JSON.stringify(payload) }),
  exportUrl: (id) => `/api/runs/${encodeURIComponent(id)}/export`,
  async security(runId, ticker) {
    const key = `${runId}:${ticker}`;
    if (!securityCache.has(key)) {
      const pending = request(`/api/runs/${encodeURIComponent(runId)}/securities/${encodeURIComponent(ticker)}`);
      securityCache.set(key, pending);
      pending.catch(() => securityCache.delete(key));
    }
    return securityCache.get(key);
  },
};
