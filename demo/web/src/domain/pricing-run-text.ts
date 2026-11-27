/** The sentences of a pricing run: running, queued, failed and cancelled (L-2). Wording belongs here, not in JSX. */
import { groupThousands } from './l1-text';
import { ALL_FIELDS, goalText } from './pricing-goals-text';
import type { PricingVersion } from './pricing-version';
import type { RunStep } from './run';
import { failureReason, formatDuration, STEP_NAMES } from './run-text';

export const PRICING_RUN_BRIEF =
  'The pricing model is setting the bike prices for Monday 08:00–09:00; then the travellers are simulated.';
export const RESULT_OPENS = 'The result opens when both steps are done.';
export const CONTINUES =
  'It continues if you open another page, and you can queue another version meanwhile.';
export const RUNNING_LABEL = 'Running…';
export const DUPLICATE = 'Duplicate';
export const PLACEHOLDER_RULE = 'placeholder rule: half price, half travel time';

export const MODEL_KEPT = '✓ kept: these goals were already solved on this instance';
export const SIMULATION_KEPT = '✓ kept: already simulated with the same prices and rule';

export function openMeanwhileLabel(letter: string): string {
  return `Open Version ${letter} meanwhile`;
}

export function instanceLine(label: string, hubPairs: number | null): string {
  const pairs = hubPairs === null ? '' : ` · ${groupThousands(hubPairs)} hub pairs with routes`;
  return `✓ City instance · ${label}${pairs}`;
}

export interface PricingStepLine {
  /** `●` for a running step, which the screen draws as a pulsing mark; null for the others. */
  readonly mark: '●' | null;
  readonly text: string;
  readonly tone: 'done' | 'running' | 'failed' | 'waiting';
}

export interface PricingStepContext {
  /** Seconds the step has been running. */
  readonly elapsedS: number;
}

function stateOf(
  step: RunStep,
  elapsedS: number,
  kept: string,
): { state: string; tone: PricingStepLine['tone'] } {
  switch (step.state) {
    case 'running':
      return { state: `running for ${formatDuration(elapsedS)}`, tone: 'running' };
    case 'kept':
      return { state: kept, tone: 'done' };
    case 'done': {
      const seconds =
        step.startedAt !== null && step.finishedAt !== null
          ? (step.finishedAt.getTime() - step.startedAt.getTime()) / 1000
          : null;
      return {
        state: seconds === null ? '✓ done' : `✓ done in ${formatDuration(seconds)}`,
        tone: 'done',
      };
    }
    case 'failed':
      return { state: '✕ failed', tone: 'failed' };
    case 'cancelled':
      return { state: 'cancelled', tone: 'waiting' };
    default:
      return { state: 'waiting', tone: 'waiting' };
  }
}

/** "5 Pricing model — running for 3 min 05 s · last time on this instance: 6 min 40 s". */
export function pricingModelLine(step: RunStep, context: PricingStepContext): PricingStepLine {
  const { state, tone } = stateOf(step, context.elapsedS, MODEL_KEPT);
  const last =
    step.state === 'running' && step.lastDurationS !== null
      ? ` · last time on this instance: ${formatDuration(step.lastDurationS)}`
      : '';
  return {
    mark: step.state === 'running' ? '●' : null,
    text: `5 ${STEP_NAMES.pricing_model} — ${state}${last}`,
    tone,
  };
}

/** "5b Traveller simulation — waiting · with Version C's prices, then with the flat price 1.00 CHF · ...". */
export function simulationLine(
  step: RunStep,
  context: PricingStepContext,
  letter: string,
  flatPrice: number,
): PricingStepLine {
  const { state, tone } = stateOf(step, context.elapsedS, SIMULATION_KEPT);
  return {
    mark: step.state === 'running' ? '●' : null,
    text: `5b ${STEP_NAMES.traveller_simulation} — ${state} · with Version ${letter}'s prices, then with the flat price ${flatPrice.toFixed(2)} CHF · ${PLACEHOLDER_RULE}`,
    tone,
  };
}

/** The finished pricing version (one with a result) of the instance version with the highest letter below `letter`. */
export function previousFinished(
  versions: readonly PricingVersion[],
  letter: string,
): PricingVersion | null {
  const below = versions
    .filter(
      (version) =>
        version.state === 'result' &&
        (version.letter.length < letter.length ||
          (version.letter.length === letter.length && version.letter < letter)),
    )
    .sort((a, b) =>
      a.letter.length === b.letter.length
        ? a.letter.localeCompare(b.letter)
        : a.letter.length - b.letter.length,
    );
  return below[below.length - 1] ?? null;
}

export interface ChangedGoal {
  readonly name: string;
  readonly before: string;
  readonly after: string;
}

/** The goals of `version` that differ from `source`, in the order of the form; none without a source. */
export function changedGoals(
  version: Pick<PricingVersion, 'goals'>,
  source: Pick<PricingVersion, 'goals'> | null,
): readonly ChangedGoal[] {
  if (source === null) return [];
  return ALL_FIELDS.filter((field) => version.goals[field.name] !== source.goals[field.name]).map(
    (field) => ({
      name: field.label,
      before: goalText(field, source.goals[field.name]),
      after: goalText(field, version.goals[field.name]),
    }),
  );
}

// ---- failures -------------------------------------------------------------------------------

const NO_SET_OF_PRICES = 'no set of prices meets every constraint';
const STOPPED_EARLY = 'the solver stopped before finding one';

/** The stored reason of `solver_no_solution` names a solver status (`status INFEASIBLE`). */
export function statusInWords(stored: string): string {
  const name = /status ([A-Z_]+)/.exec(stored)?.[1];
  return name === 'INFEASIBLE' || name === 'INF_OR_UNBD' ? NO_SET_OF_PRICES : STOPPED_EARLY;
}

/** The check a `simulation_check_failed` reason names: the text after "check: ". */
export function checkOf(stored: string): string {
  const at = stored.indexOf('check: ');
  return at < 0 ? stored : stored.slice(at + 'check: '.length).replace(/\.$/, '');
}

/** The reason sentence of a failed pricing step by its code; the stored reason for a code it does not know. */
export function pricingFailureReason(code: string, stored: string): string {
  switch (code) {
    case 'solver_size_limited':
      return "Gurobi's size-limited licence cannot solve this instance";
    case 'solver_no_solution':
      return `the solver ended without a solution (${statusInWords(stored)})`;
    case 'simulation_check_failed':
      return `the traveller simulation broke its check (${checkOf(stored)}); nothing was stored. The pricing model's result is kept.`;
    default:
      return failureReason(code, null, stored);
  }
}

export function runAgainLabel(failedStep: 'pricing_model' | 'traveller_simulation'): string {
  return `Run again from ${STEP_NAMES[failedStep]}`;
}

/** "✓ Version C: result ready", the run line when a pricing run ended while another view was open. */
export function runLineResultReady(name: string): string {
  return `✓ ${name}: result ready`;
}
