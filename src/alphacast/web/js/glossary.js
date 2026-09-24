// Short definitions for the workstation's technical terms, shown on hover or focus.

import { escapeHtml } from './format.js';

export const DEFINITIONS = {
  rank_ic: ['Rank IC', 'Spearman correlation between a model\'s scores and the realised sector-relative returns in one month. 0 is no skill; real equity signals are usually 0.02 to 0.05.'],
  ic_ir: ['IC information ratio', 'Mean Rank IC divided by its month-to-month volatility: how consistent the ranking skill is.'],
  t_stat: ['t-statistic', 'Mean Rank IC divided by its standard error. Around 2 or more is conventionally significant for a single test.'],
  holm: ['Holm-adjusted p-value', 'The p-value corrected for comparing several models, since the best of many looks better than it is. Below 0.05 is conventionally significant.'],
  spread: ['Q1 − Q5 spread', 'Average sector-relative return of the top-scored fifth minus the bottom fifth over the next 20 sessions.'],
  sharpe: ['Sharpe ratio', 'Annualised return divided by annualised volatility, from monthly returns. Net means after trading costs.'],
  info_ratio: ['Information ratio', 'Annualised return over the equal-weight universe divided by the volatility of that difference.'],
  turnover: ['Turnover', 'One-way share of the book traded at a rebalance. 100% means the whole portfolio was replaced.'],
  drawdown: ['Max drawdown', 'The largest fall from a running peak in value, counting the starting balance as the first peak.'],
  psi: ['Population stability index', 'How far a feature\'s recent distribution has moved from its history. Under 0.10 is stable; above 0.25 has shifted.'],
  consensus: ['Consensus', 'How many models place the stock in their top fifth today. The ensemble does not vote, since it is built from the others.'],
  percentile: ['Score percentile', 'Where the model\'s score for this stock sits in today\'s cross-section. 100 is the most attractive.'],
  beta: ['Beta', 'How much the sleeve moves with the equal-weight universe. Above 1 means it amplifies market moves, which lifts returns in a rising market without any stock-picking skill.'],
  alpha: ['Alpha', 'Annualised return left after removing the sleeve\'s market exposure (beta), from a regression of monthly returns on the universe.'],
  health: ['Model health', 'The last six months\' mean Rank IC tested against the model\'s earlier record. Degraded if it is more than two standard errors below; watch if more than one below, or below zero.'],
};

/** A label that explains itself on hover and keyboard focus. */
export function term(key, text = DEFINITIONS[key]?.[0]) {
  return `<span class="term" tabindex="0" data-term="${escapeHtml(key)}">${escapeHtml(text)}</span>`;
}

export const definition = (key) => DEFINITIONS[key]?.[1] || '';
