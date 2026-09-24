// Formatting and small DOM helpers shared by every view.

const MISSING = '—';

export const isNum = (value) => typeof value === 'number' && Number.isFinite(value);

export function pct(value, digits = 1, { sign = false } = {}) {
  if (!isNum(value)) return MISSING;
  value = unsign(value, digits + 2);
  const text = `${(value * 100).toFixed(digits)}%`;
  return sign && value > 0 ? `+${text}` : text;
}

// Values that round to zero print without a sign, never as "-0.000".
const unsign = (value, digits) => (Math.abs(value) < 0.5 * 10 ** -digits ? 0 : value);

export function num(value, digits = 2, { sign = false } = {}) {
  if (!isNum(value)) return MISSING;
  value = unsign(value, digits);
  const text = value.toFixed(digits);
  return sign && value > 0 ? `+${text}` : text;
}

export function int(value) {
  return isNum(value) ? Math.round(value).toLocaleString('en-US') : MISSING;
}

export function money(value) {
  if (!isNum(value)) return MISSING;
  return value.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 });
}

export function compact(value) {
  if (!isNum(value)) return MISSING;
  return Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(value);
}

export function date(value, style = 'medium') {
  if (!value) return MISSING;
  const parsed = new Date(`${String(value).slice(0, 10)}T00:00:00`);
  const options = style === 'short'
    ? { month: 'short', year: '2-digit' }
    : { month: 'short', day: 'numeric', year: 'numeric' };
  return parsed.toLocaleDateString('en-US', options);
}

export function toneClass(value) {
  if (!isNum(value) || value === 0) return '';
  return value > 0 ? 'pos' : 'neg';
}

export const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (character) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
}[character]));

/** Tagged template that escapes interpolations unless they are wrapped with raw(). */
export function html(strings, ...values) {
  return strings.reduce((output, part, index) => {
    if (index >= values.length) return output + part;
    const value = values[index];
    const rendered = Array.isArray(value)
      ? value.map((item) => (item && item.__raw !== undefined ? item.__raw : escapeHtml(item))).join('')
      : value && value.__raw !== undefined ? value.__raw : escapeHtml(value);
    return output + part + rendered;
  }, '');
}

export const raw = (value) => ({ __raw: String(value ?? '') });

export function sectorShort(sector) {
  return ({
    'Information Technology': 'Info Tech',
    'Communication Services': 'Comm Services',
    'Consumer Discretionary': 'Cons Discretionary',
    'Consumer Staples': 'Cons Staples',
  })[sector] || sector;
}

export function mean(values) {
  const valid = values.filter(isNum);
  return valid.length ? valid.reduce((sum, value) => sum + value, 0) / valid.length : NaN;
}

export function std(values) {
  const valid = values.filter(isNum);
  if (valid.length < 2) return NaN;
  const average = mean(valid);
  return Math.sqrt(valid.reduce((sum, value) => sum + (value - average) ** 2, 0) / (valid.length - 1));
}

export function rolling(values, window, reducer = mean) {
  return values.map((_, index) => (index + 1 < window ? NaN : reducer(values.slice(index + 1 - window, index + 1))));
}

export function cumulative(returns) {
  let wealth = 1;
  return returns.map((value) => { wealth *= 1 + (isNum(value) ? value : 0); return wealth; });
}

export function drawdowns(wealth) {
  let peak = 1;
  return wealth.map((value) => { peak = Math.max(peak, value); return value / peak - 1; });
}

export function downloadFile(filename, content, type = 'text/csv') {
  const blob = new Blob([content], { type });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}

export function toCsv(rows, columns) {
  const cell = (value) => {
    const text = value === null || value === undefined ? '' : String(value);
    return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  };
  return [columns.map((column) => cell(column.label)).join(','),
    ...rows.map((row) => columns.map((column) => cell(column.csv ? column.csv(row) : row[column.key])).join(','))].join('\n');
}

export function cadence(everyFolds) {
  return ({ 1: 'monthly', 2: 'every two months', 3: 'quarterly' })[everyFolds || 1] || `every ${everyFolds} months`;
}
