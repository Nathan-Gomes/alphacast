// Dependency-free SVG charts with a shared hover layer.
// Colours are CSS custom properties, so every chart follows the active theme.

import { date, escapeHtml, isNum } from './format.js';

const tooltip = () => document.getElementById('tooltip');
const NS = 'http://www.w3.org/2000/svg';

export function showTooltip(event, content) {
  const element = tooltip();
  element.innerHTML = content;
  element.hidden = false;
  const { innerWidth, innerHeight } = window;
  const box = element.getBoundingClientRect();
  let left = event.clientX + 14;
  let top = event.clientY + 14;
  if (left + box.width > innerWidth - 8) left = event.clientX - box.width - 14;
  if (top + box.height > innerHeight - 8) top = event.clientY - box.height - 14;
  element.style.left = `${Math.max(8, left)}px`;
  element.style.top = `${Math.max(8, top)}px`;
}

export function hideTooltip() {
  const element = tooltip();
  if (element) element.hidden = true;
}

export function tooltipHtml(title, rows) {
  return `<div class="tt-title">${escapeHtml(title)}</div>${rows.map((row) => `
    <div class="tt-row"><span class="tt-key">${row.color ? `<i style="background:${row.color}"></i>` : ''}${escapeHtml(row.label)}</span><b>${escapeHtml(row.value)}</b></div>`).join('')}`;
}

function niceTicks(min, max, count = 5) {
  if (!isNum(min) || !isNum(max)) return [0];
  if (min === max) { min -= 1; max += 1; }
  const span = max - min;
  const step0 = span / count;
  const magnitude = 10 ** Math.floor(Math.log10(step0));
  const residual = step0 / magnitude;
  const step = (residual > 5 ? 10 : residual > 2 ? 5 : residual > 1 ? 2 : 1) * magnitude;
  const ticks = [];
  for (let value = Math.ceil(min / step) * step; value <= max + step * 1e-9; value += step) {
    ticks.push(Math.abs(value) < step * 1e-9 ? 0 : value);
  }
  return ticks;
}

function extent(arrays, include = []) {
  let min = Infinity;
  let max = -Infinity;
  for (const values of arrays) {
    for (const value of values) {
      if (isNum(value)) { min = Math.min(min, value); max = Math.max(max, value); }
    }
  }
  for (const value of include) { min = Math.min(min, value); max = Math.max(max, value); }
  if (!isNum(min)) return [0, 1];
  const pad = (max - min || Math.abs(max) || 1) * 0.06;
  return [min - pad, max + pad];
}

function frame(container, height, label) {
  container.classList.add('chart');
  container.innerHTML = '';
  const width = Math.max(container.clientWidth, 280);
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  svg.setAttribute('height', height);
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', label);
  container.append(svg);
  return { svg, width };
}

function yAxis(ticks, scaleY, left, right, format) {
  return ticks.map((tick) => `
    <line class="grid-line" x1="${left}" x2="${right}" y1="${scaleY(tick)}" y2="${scaleY(tick)}"/>
    <text x="${left - 8}" y="${scaleY(tick) + 3.5}" text-anchor="end">${escapeHtml(format(tick))}</text>`).join('');
}

function xLabels(dates, scaleX, bottom, count, format = (value) => date(value, 'short')) {
  if (!dates.length) return '';
  const step = Math.max(1, Math.ceil(dates.length / count));
  const indices = [];
  for (let index = 0; index < dates.length; index += step) indices.push(index);
  // Edge labels anchor inward so they never clip at the plot boundary.
  const anchor = (index) => (index === 0 && indices.length > 1 ? 'start' : index === dates.length - 1 ? 'end' : 'middle');
  return indices.map((index) => `<text x="${scaleX(index)}" y="${bottom + 18}" text-anchor="${anchor(index)}">${escapeHtml(format(dates[index]))}</text>`).join('');
}

function linePath(values, scaleX, scaleY) {
  let path = '';
  let drawing = false;
  values.forEach((value, index) => {
    if (!isNum(value)) { drawing = false; return; }
    path += `${drawing ? 'L' : 'M'}${scaleX(index).toFixed(1)},${scaleY(value).toFixed(1)}`;
    drawing = true;
  });
  return path;
}

/**
 * Arrow keys, Home and End step through points on a focused chart; the tooltip
 * anchors to the point instead of the pointer. showAt(index, anchorX) draws it.
 */
function keyboardNavigation(svg, count, showAt, hide, scaleX, width) {
  let current = count - 1;
  svg.setAttribute('tabindex', '0');
  svg.setAttribute('aria-describedby', 'chart-keys');
  const anchor = (index) => {
    const box = svg.getBoundingClientRect();
    return { clientX: box.left + (scaleX(index) / width) * box.width, clientY: box.top + box.height * 0.3 };
  };
  svg.addEventListener('focus', () => showAt(current, anchor(current)));
  svg.addEventListener('blur', hide);
  svg.addEventListener('keydown', (event) => {
    const step = { ArrowLeft: -1, ArrowRight: 1, Home: -Infinity, End: Infinity }[event.key];
    if (step === undefined) return;
    event.preventDefault();
    current = Math.max(0, Math.min(count - 1, current + (Number.isFinite(step) ? step * (event.shiftKey ? 10 : 1) : step)));
    showAt(current, anchor(current));
  });
}

export function legend(items) {
  return `<div class="legend">${items.map((item) => `<span><i class="${item.dash ? 'dash' : ''}" style="background:${item.color};color:${item.color}"></i>${escapeHtml(item.label)}</span>`).join('')}</div>`;
}

/**
 * Multi-series line chart on one shared y-axis.
 * series: [{ label, color, values, dash?, area?, width? }]
 * band: optional { lower, upper, color } shaded range.
 */
export function lineChart(container, {
  dates, series, height = 260, yFormat = (value) => value.toFixed(2), baseline = null,
  band = null, label = 'Line chart', tooltipFormat = yFormat, markers = null, xFormat = null,
}) {
  const { svg, width } = frame(container, height, label);
  const margin = { top: 12, right: 14, bottom: 28, left: 54 };
  const right = width - margin.right;
  const bottom = height - margin.bottom;
  const include = baseline === null ? [] : [baseline];
  const [min, max] = extent([...series.map((item) => item.values), ...(band ? [band.lower, band.upper] : [])], include);
  const ticks = niceTicks(min, max, Math.max(3, Math.round(height / 60)));
  const lo = Math.min(min, ticks[0]);
  const hi = Math.max(max, ticks[ticks.length - 1]);
  const count = Math.max(dates.length - 1, 1);
  const scaleX = (index) => margin.left + (index / count) * (right - margin.left);
  const scaleY = (value) => bottom - ((value - lo) / (hi - lo || 1)) * (bottom - margin.top);

  let body = yAxis(ticks, scaleY, margin.left, right, yFormat);
  body += `<line class="axis-line" x1="${margin.left}" x2="${right}" y1="${bottom}" y2="${bottom}"/>`;
  if (baseline !== null) {
    body += `<line x1="${margin.left}" x2="${right}" y1="${scaleY(baseline)}" y2="${scaleY(baseline)}" stroke="var(--axis)" stroke-width="1.2"/>`;
  }
  if (band) {
    const upper = band.upper.map((value, index) => `${index ? 'L' : 'M'}${scaleX(index).toFixed(1)},${scaleY(value).toFixed(1)}`).join('');
    const lower = band.lower.map((value, index) => `L${scaleX(index).toFixed(1)},${scaleY(value).toFixed(1)}`).reverse().join('');
    body += `<path d="${upper}${lower}Z" fill="${band.color}" opacity="0.14"/>`;
  }
  for (const item of series) {
    if (item.area) {
      const first = item.values.findIndex(isNum);
      const path = linePath(item.values, scaleX, scaleY);
      const base = scaleY(baseline ?? lo);
      body += `<path d="${path}L${scaleX(item.values.length - 1)},${base}L${scaleX(first)},${base}Z" fill="${item.color}" opacity="0.16"/>`;
    }
    body += `<path d="${linePath(item.values, scaleX, scaleY)}" fill="none" stroke="${item.color}" stroke-width="${item.width || 2}" stroke-linejoin="round" stroke-linecap="round" ${item.dash ? 'stroke-dasharray="5 4"' : ''}/>`;
  }
  if (markers) {
    body += markers.map((marker) => `<circle cx="${scaleX(marker.index)}" cy="${scaleY(marker.value)}" r="4" fill="${marker.color}" stroke="var(--surface)" stroke-width="2"/>`).join('');
  }
  body += xLabels(dates, scaleX, bottom, Math.max(3, Math.floor(width / 110)), xFormat || undefined);
  body += `<g class="hover" visibility="hidden"><line class="crosshair" y1="${margin.top}" y2="${bottom}"/>${series.map((item) => `<circle r="4" fill="${item.color}" stroke="var(--surface)" stroke-width="2"/>`).join('')}</g>`;
  body += `<rect class="hit" x="${margin.left}" y="0" width="${right - margin.left}" height="${bottom}"/>`;
  svg.innerHTML = body;

  const hover = svg.querySelector('.hover');
  const line = hover.querySelector('line');
  const dots = [...hover.querySelectorAll('circle')];
  const hit = svg.querySelector('.hit');
  const showAt = (index, event) => {
    const cx = scaleX(index);
    line.setAttribute('x1', cx);
    line.setAttribute('x2', cx);
    dots.forEach((dot, position) => {
      const value = series[position].values[index];
      dot.setAttribute('visibility', isNum(value) ? 'visible' : 'hidden');
      if (isNum(value)) { dot.setAttribute('cx', cx); dot.setAttribute('cy', scaleY(value)); }
    });
    hover.setAttribute('visibility', 'visible');
    showTooltip(event, tooltipHtml(xFormat ? xFormat(dates[index]) : date(dates[index]), series.map((item) => ({
      label: item.label, color: item.color, value: isNum(item.values[index]) ? tooltipFormat(item.values[index]) : '—',
    }))));
  };
  const hide = () => { hover.setAttribute('visibility', 'hidden'); hideTooltip(); };
  hit.addEventListener('pointermove', (event) => {
    const box = svg.getBoundingClientRect();
    const x = ((event.clientX - box.left) / box.width) * width;
    showAt(Math.max(0, Math.min(dates.length - 1, Math.round(((x - margin.left) / (right - margin.left)) * count))), event);
  });
  hit.addEventListener('pointerleave', hide);
  keyboardNavigation(svg, dates.length, showAt, hide, scaleX, width);
}

/** Signed columns over time with an optional overlay line (e.g. rolling mean). */
export function columnChart(container, {
  dates, values, height = 240, yFormat = (value) => value.toFixed(2), label = 'Column chart',
  overlay = null, positive = 'var(--series-1)', negative = 'var(--series-2)', tooltipRows = null,
}) {
  const { svg, width } = frame(container, height, label);
  const margin = { top: 12, right: 14, bottom: 28, left: 54 };
  const right = width - margin.right;
  const bottom = height - margin.bottom;
  const [min, max] = extent([values, overlay ? overlay.values : []], [0]);
  const ticks = niceTicks(min, max, 4);
  const lo = Math.min(min, ticks[0]);
  const hi = Math.max(max, ticks[ticks.length - 1]);
  const slot = (right - margin.left) / Math.max(values.length, 1);
  const barWidth = Math.max(1, Math.min(18, slot - Math.min(2, slot * 0.3)));
  const scaleX = (index) => margin.left + slot * (index + 0.5);
  const scaleY = (value) => bottom - ((value - lo) / (hi - lo || 1)) * (bottom - margin.top);
  const zero = scaleY(0);
  let body = yAxis(ticks, scaleY, margin.left, right, yFormat);
  body += values.map((value, index) => {
    if (!isNum(value)) return '';
    const y = Math.min(zero, scaleY(value));
    const barHeight = Math.max(1, Math.abs(scaleY(value) - zero));
    return `<rect x="${(scaleX(index) - barWidth / 2).toFixed(1)}" y="${y.toFixed(1)}" width="${barWidth.toFixed(1)}" height="${barHeight.toFixed(1)}" rx="${Math.min(2, barWidth / 2)}" fill="${value >= 0 ? positive : negative}"/>`;
  }).join('');
  body += `<line class="axis-line" x1="${margin.left}" x2="${right}" y1="${zero}" y2="${zero}"/>`;
  if (overlay) {
    body += `<path d="${linePath(overlay.values, scaleX, scaleY)}" fill="none" stroke="${overlay.color}" stroke-width="2"/>`;
  }
  body += xLabels(dates, scaleX, bottom, Math.max(3, Math.floor(width / 110)));
  body += `<line class="crosshair" visibility="hidden" y1="${margin.top}" y2="${bottom}"/>`;
  body += `<rect class="hit" x="${margin.left}" y="0" width="${right - margin.left}" height="${bottom}"/>`;
  svg.innerHTML = body;
  const cross = svg.querySelector('.crosshair');
  const hit = svg.querySelector('.hit');
  const showAt = (index, event) => {
    cross.setAttribute('x1', scaleX(index));
    cross.setAttribute('x2', scaleX(index));
    cross.setAttribute('visibility', 'visible');
    const rows = tooltipRows ? tooltipRows(index) : [{ label: 'Value', value: yFormat(values[index]) }];
    if (overlay && !tooltipRows) rows.push({ label: overlay.label, color: overlay.color, value: isNum(overlay.values[index]) ? yFormat(overlay.values[index]) : '—' });
    showTooltip(event, tooltipHtml(date(dates[index]), rows));
  };
  const hide = () => { cross.setAttribute('visibility', 'hidden'); hideTooltip(); };
  hit.addEventListener('pointermove', (event) => {
    const box = svg.getBoundingClientRect();
    const x = ((event.clientX - box.left) / box.width) * width;
    showAt(Math.max(0, Math.min(values.length - 1, Math.floor((x - margin.left) / slot))), event);
  });
  hit.addEventListener('pointerleave', hide);
  keyboardNavigation(svg, values.length, showAt, hide, scaleX, width);
}

/** Vertical bars for a handful of categories, e.g. quintiles. */
export function categoryBars(container, {
  labels, values, colors, height = 230, yFormat = (value) => value.toFixed(2), label = 'Bar chart',
  tooltipRows = null,
}) {
  const { svg, width } = frame(container, height, label);
  const margin = { top: 16, right: 14, bottom: 30, left: 54 };
  const right = width - margin.right;
  const bottom = height - margin.bottom;
  const [min, max] = extent([values], [0]);
  const ticks = niceTicks(min, max, 4);
  const lo = Math.min(min, ticks[0]);
  const hi = Math.max(max, ticks[ticks.length - 1]);
  const slot = (right - margin.left) / values.length;
  const barWidth = Math.min(64, slot * 0.62);
  const scaleY = (value) => bottom - ((value - lo) / (hi - lo || 1)) * (bottom - margin.top);
  const zero = scaleY(0);
  let body = yAxis(ticks, scaleY, margin.left, right, yFormat);
  body += values.map((value, index) => {
    const x = margin.left + slot * index + (slot - barWidth) / 2;
    const y = Math.min(zero, scaleY(value));
    return `<rect x="${x}" y="${y}" width="${barWidth}" height="${Math.max(1, Math.abs(scaleY(value) - zero))}" rx="3" fill="${colors ? colors[index] : 'var(--series-1)'}"/>
      <text x="${x + barWidth / 2}" y="${value >= 0 ? y - 5 : y + Math.abs(scaleY(value) - zero) + 13}" text-anchor="middle" style="fill:var(--ink)">${escapeHtml(yFormat(value))}</text>
      <text x="${x + barWidth / 2}" y="${bottom + 18}" text-anchor="middle">${escapeHtml(labels[index])}</text>
      <rect class="hit" data-index="${index}" x="${margin.left + slot * index}" y="${margin.top}" width="${slot}" height="${bottom - margin.top}"/>`;
  }).join('');
  body += `<line class="axis-line" x1="${margin.left}" x2="${right}" y1="${zero}" y2="${zero}"/>`;
  svg.innerHTML = body;
  svg.querySelectorAll('.hit').forEach((hit) => {
    const index = Number(hit.dataset.index);
    hit.addEventListener('pointermove', (event) => showTooltip(event, tooltipHtml(labels[index],
      tooltipRows ? tooltipRows(index) : [{ label: 'Value', value: yFormat(values[index]) }])));
    hit.addEventListener('pointerleave', hideTooltip);
  });
}

/** Horizontal bars in HTML. Signed values grow from a centred zero line. */
export function hbars(items, { format = (value) => value.toFixed(2), signed = false, color = 'var(--series-1)', negativeColor = 'var(--series-2)' } = {}) {
  const maxAbs = Math.max(...items.map((item) => Math.abs(item.value)), 1e-9);
  return `<div class="hbars">${items.map((item) => {
    const share = Math.abs(item.value) / maxAbs;
    const fill = item.color || (item.value < 0 ? negativeColor : color);
    const bar = signed
      ? `<b style="background:${fill};${item.value >= 0 ? `left:50%;width:${share * 50}%` : `right:50%;width:${share * 50}%`}"></b><span class="zero" style="left:50%"></span>`
      : `<b style="background:${fill};left:0;width:${Math.max(share * 100, 0.5)}%"></b>`;
    return `<div class="hbar" ${item.title ? `title="${escapeHtml(item.title)}"` : ''}><span class="name">${escapeHtml(item.label)}</span><span class="track">${bar}</span><span class="val">${escapeHtml(format(item.value))}</span></div>`;
  }).join('')}</div>`;
}

/**
 * Two bars per row (e.g. portfolio vs universe) on one scale, with a right-hand value.
 * items: [{ label, a, b, value, tone?, title? }]
 */
export function pairedBars(items, { labelA, labelB, colorA = 'var(--series-1)', colorB = 'var(--bench)', format = (value) => value }) {
  const max = Math.max(...items.flatMap((item) => [item.a, item.b]), 1e-9);
  return `${legend([{ label: labelA, color: colorA }, { label: labelB, color: colorB }])}
    <div class="hbars">${items.map((item) => `
      <div class="hbar"${item.title ? ` title="${escapeHtml(item.title)}"` : ''}>
        <span class="name">${escapeHtml(item.label)}</span>
        <span class="track paired">
          <b class="bar-a" style="width:${(item.a / max) * 100}%;background:${colorA}"></b>
          <b class="bar-b" style="width:${(item.b / max) * 100}%;background:${colorB}"></b>
        </span>
        <span class="val ${item.tone || ''}">${escapeHtml(format(item.value))}</span>
      </div>`).join('')}</div>`;
}
