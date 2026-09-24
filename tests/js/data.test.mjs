import assert from 'node:assert/strict';
import { test } from 'node:test';

import { consensus, leadingModel, rankAgreement, votingModels } from '../../src/alphacast/web/js/data.js';

const live = (ranks) => ranks.map(([ticker, rank, quintile]) => ({ ticker, rank, quintile }));
const index = {
  models: ['a', 'b', 'c'],
  summaries: { a: { mean_rank_ic: 0.01 }, b: { mean_rank_ic: 0.03 }, c: { mean_rank_ic: -0.01 } },
  live: {
    a: live([['X', 1, 1], ['Y', 2, 2], ['Z', 3, 5]]),
    b: live([['X', 1, 1], ['Y', 2, 2], ['Z', 3, 5]]),
    c: live([['X', 3, 5], ['Y', 2, 2], ['Z', 1, 1]]),
  },
};

test('agreement is 1 for identical rankings and -1 for reversed ones', () => {
  assert.equal(rankAgreement(index, 'a', 'b'), 1);
  assert.equal(rankAgreement(index, 'a', 'c'), -1);
});

test('consensus counts top-quintile placements across models', () => {
  assert.deepEqual(consensus(index), { X: 2, Y: 0, Z: 1 });
});

test('the leading model has the highest mean rank IC', () => {
  assert.equal(leadingModel(index), 'b');
});

test('the ensemble does not vote in consensus', () => {
  const withEnsemble = { ...index, models: [...index.models, 'ensemble'], live: { ...index.live, ensemble: live([['X', 1, 1], ['Y', 2, 2], ['Z', 3, 5]]) } };
  assert.deepEqual(votingModels(withEnsemble), ['a', 'b', 'c']);
  assert.deepEqual(consensus(withEnsemble), { X: 2, Y: 0, Z: 1 });
});
