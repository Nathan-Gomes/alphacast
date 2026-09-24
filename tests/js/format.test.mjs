import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  cumulative, drawdowns, escapeHtml, html, mean, num, pct, raw, rolling, std, toCsv,
} from '../../src/alphacast/web/js/format.js';

test('numbers that round to zero never print a minus sign', () => {
  assert.equal(num(-0.0001, 3), '0.000');
  assert.equal(pct(-0.00001, 1), '0.0%');
  assert.equal(num(-0.012, 3), '-0.012');
  assert.equal(num(0.4, 2, { sign: true }), '+0.40');
  assert.equal(num(NaN), '—');
});

test('html escapes interpolations unless marked raw', () => {
  assert.equal(html`<b>${'<script>'}</b>`, '<b>&lt;script&gt;</b>');
  assert.equal(html`<b>${raw('<i>ok</i>')}</b>`, '<b><i>ok</i></b>');
  assert.equal(escapeHtml(`"'&`), '&quot;&#39;&amp;');
});

test('csv quotes cells that need it', () => {
  const csv = toCsv([{ a: 'x,y', b: 'say "hi"' }], [{ key: 'a', label: 'a' }, { key: 'b', label: 'b' }]);
  assert.equal(csv, 'a,b\n"x,y","say ""hi"""');
});

test('wealth, drawdown and rolling statistics', () => {
  assert.deepEqual(cumulative([0.1, -0.5]).map((v) => +v.toFixed(4)), [1.1, 0.55]);
  assert.deepEqual(drawdowns([1.1, 0.55, 1.2]).map((v) => +v.toFixed(4)), [0, -0.5, 0]);
  assert.equal(mean([1, 2, NaN, 3]), 2);
  assert.equal(+std([1, 2, 3]).toFixed(6), 1);
  const r = rolling([1, 2, 3, 4], 2);
  assert.ok(Number.isNaN(r[0]));
  assert.deepEqual(r.slice(1), [1.5, 2.5, 3.5]);
});
