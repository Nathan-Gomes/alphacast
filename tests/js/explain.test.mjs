import assert from 'node:assert/strict';
import { test } from 'node:test';

import { explainRank } from '../../src/alphacast/web/js/explain.js';

const labels = { a: '6M return', b: '20D volatility', c: '1M return', d: 'Relative volume' };

test('ordinary labels are lower-cased mid-sentence', () => {
  const text = explainRank({ ticker: 'X', rank: 1, total: 5, modelLabel: 'M', labels, attribution: [{ feature: 'd', contribution: 1, percentile: 99 }] });
  assert.equal(text, 'X ranks 1st of 5 under M, lifted most by its relative volume (99th percentile).');
});

test('names the strongest drivers in each direction', () => {
  const text = explainRank({
    ticker: 'NVDA', rank: 22, total: 98, modelLabel: 'Ridge', labels,
    attribution: [
      { feature: 'a', contribution: 0.03, percentile: 91 },
      { feature: 'b', contribution: 0.01, percentile: 12.4 },
      { feature: 'c', contribution: -0.02, percentile: 3 },
      { feature: 'd', contribution: 0, percentile: 50 },
    ],
  });
  assert.equal(text, 'NVDA ranks 22nd of 98 under Ridge, lifted most by its 6M return (91st percentile) and 20D volatility (12th percentile) and held back by its 1M return (3rd percentile).');
});

test('handles a score no feature moves', () => {
  const text = explainRank({ ticker: 'X', rank: 11, total: 20, modelLabel: 'M', labels, attribution: [{ feature: 'a', contribution: 0, percentile: 50 }] });
  assert.equal(text, 'X ranks 11th of 20 under M; no single feature moves its score.');
});
