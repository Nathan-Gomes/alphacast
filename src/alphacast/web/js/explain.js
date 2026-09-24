// Plain-language summary of a security's attribution. Pure function, so it is tested.

const ordinal = (n) => {
  const value = Math.round(n);
  const suffix = value % 100 >= 11 && value % 100 <= 13 ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' })[value % 10] || 'th';
  return `${value}${suffix}`;
};

// Lower-case ordinary words ("Relative volume") but keep abbreviations ("6M return").
const inSentence = (label) => (/^[A-Z][a-z]/.test(label) ? label[0].toLowerCase() + label.slice(1) : label);

const describe = (row, labels) => `${inSentence(labels[row.feature])} (${ordinal(row.percentile)} percentile)`;

const list = (items) => (items.length > 1 ? `${items.slice(0, -1).join(', ')} and ${items.at(-1)}` : items[0]);

/**
 * attribution: [{ feature, contribution, percentile }]; labels: feature id -> label.
 * Returns one sentence naming the two strongest drivers each way.
 */
export function explainRank({ ticker, rank, total, modelLabel, attribution, labels }) {
  const meaningful = attribution.filter((row) => Math.abs(row.contribution) > 1e-9);
  const ups = meaningful.filter((row) => row.contribution > 0).sort((a, b) => b.contribution - a.contribution).slice(0, 2);
  const downs = meaningful.filter((row) => row.contribution < 0).sort((a, b) => a.contribution - b.contribution).slice(0, 2);
  const head = `${ticker} ranks ${ordinal(rank)} of ${total} under ${modelLabel}`;
  if (!ups.length && !downs.length) return `${head}; no single feature moves its score.`;
  const lifted = ups.length ? `lifted most by its ${list(ups.map((row) => describe(row, labels)))}` : '';
  const held = downs.length ? `held back by its ${list(downs.map((row) => describe(row, labels)))}` : '';
  return `${head}, ${[lifted, held].filter(Boolean).join(' and ')}.`;
}
