import { formatDuration } from './run-text';
import type { PricingResult } from './pricing-result';
import type { SimulationRuleRef, Verdict } from './system-status';

export const SIMULATION_OFF = 'Simulation is off: the runner is not running.';
export const STORED_RESULTS_STAY = 'Stored results stay available.';
export const SIMULATING = '● simulating';

export interface OlderRule {
  /** The rule version of the stored simulations. */
  readonly old: number;
  /** The rule version the Lab simulates with now. */
  readonly new: number;
}

/**
 * The older rule of a result: null when its simulations used the current rule, and null when
 * the current rule is not known (a `rule_current` of false is then no evidence of an older one).
 */
export function olderRule(
  result: Pick<PricingResult, 'simulations'>,
  current: SimulationRuleRef | null,
): OlderRule | null {
  if (current === null) return null;
  const { modelPrices, flat } = result.simulations;
  const older = !modelPrices.ruleCurrent ? modelPrices : !flat.ruleCurrent ? flat : null;
  return older === null ? null : { old: older.ruleVersion, new: current.version };
}

export function olderRuleBox(old: number, current: number): string {
  return `Simulated with an older rule. These simulations used the placeholder rule v${String(old)}; the Lab now simulates with v${String(current)}. The pricing model's numbers do not change.`;
}

export function simulateAgainLabel(current: number): string {
  return `Simulate again with v${String(current)}`;
}

export function olderRuleSuffix(old: number): string {
  return ` · older rule (v${String(old)})`;
}

/** The running line without its pulsing mark. */
export function simulatingLine(elapsedS: number): string {
  return `Traveller simulation · running for ${formatDuration(elapsedS)}`;
}

/** Why simulating is off: the runner's own sentence, else the API's first reason. */
export function simulationOffReason(verdict: Verdict): string {
  const [first] = verdict.reasons;
  if (first === undefined || first.component === 'runner') return SIMULATION_OFF;
  return `Simulation is off: ${first.reason.replace(/\.$/, '')}.`;
}

export function pricingDeleteQuestion(letter: string, name: string, instanceLabel: string): string {
  return `Delete Version ${letter} · ${name}? This removes its goals and its result. Other versions of ${instanceLabel} stay. This cannot be undone.`;
}

export function pricingDeleteAction(letter: string): string {
  return `Delete Version ${letter}`;
}

export function isShowcaseNote(letter: string): string {
  return `Version ${letter} is the home page's result: choose another one first.`;
}
