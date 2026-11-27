/** The sentences of a build in progress, a failed one and a cancelled one. Wording belongs here, not in JSX. */
import type { InstanceMenuEntry, PlannedStep, StepName } from './city-instance';
import { formatInstantDay, groupThousands, longDate, menuVersionState } from './l1-text';
import { ordinal } from './ordinal';
import type { Run, RunKind, RunStep } from './run';

export { ordinal };
export const menuRunState = menuVersionState;

export const NO_RUN = 'No run in progress';
export const PRICING_VERSIONS_OFF = 'Available when the instance is built.';

export const STEP_NAMES: Readonly<Record<StepName, string>> = {
  area: 'Area',
  hubs: 'Hubs',
  routes: 'Routes',
  travellers_and_bikes: 'Travellers and bikes',
  pricing_model: 'Pricing model',
  traveller_simulation: 'Traveller simulation',
};

/** 252 → "4 min 12 s"; 42 → "42 s"; 3780 → "1 h 03 min". Whole seconds, never negative. */
export function formatDuration(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds));
  if (whole < 60) return `${String(whole)} s`;
  if (whole < 3600) return `${String(Math.floor(whole / 60))} min ${String(whole % 60)} s`;
  const minutes = Math.floor((whole % 3600) / 60);
  return `${String(Math.floor(whole / 3600))} h ${String(minutes).padStart(2, '0')} min`;
}

/** The name of a step as the API writes it; the text itself for one this screen does not know. */
export function stepNameOf(step: string): string {
  return (STEP_NAMES as Readonly<Record<string, string | undefined>>)[step] ?? step;
}

export function lastTimeSentence(seconds: number): string {
  return `Last time on this instance: ${formatDuration(seconds)}.`;
}

/**
 * Whole seconds since `since` (the run's start by default) on the server's clock: the browser's
 * clock offset by the server time seen when the answer arrived. It stops at the moment of the
 * last answer while the runner is not alive.
 */
export function elapsedSeconds(
  run: Pick<Run, 'startedAt' | 'serverTime' | 'runner'>,
  browserAtAnswer: number,
  browserNow: number,
  since: Date | null = run.startedAt,
): number {
  if (since === null) return 0;
  const now = run.runner.alive ? browserNow : browserAtAnswer;
  const serverNow = now + (run.serverTime.getTime() - browserAtAnswer);
  return Math.max(0, Math.floor((serverNow - since.getTime()) / 1000));
}

// ---- the steps ------------------------------------------------------------------------------

function count(counts: Readonly<Record<string, unknown>>, key: string): number | null {
  const value = counts[key];
  return typeof value === 'number' ? value : null;
}

function countsText(step: RunStep): string {
  const { counts } = step;
  switch (step.step) {
    case 'area': {
      const stops = count(counts, 'stops');
      const stations = count(counts, 'bike_stations');
      return [
        stops === null ? null : `${groupThousands(stops)} stops and platforms`,
        stations === null ? null : `${groupThousands(stations)} bike stations`,
      ]
        .filter((part) => part !== null)
        .join(' · ');
    }
    case 'hubs': {
      const hubs = count(counts, 'hubs');
      return hubs === null ? '' : `${groupThousands(hubs)} hubs`;
    }
    case 'routes': {
      const pairs = count(counts, 'hub_pairs_with_routes');
      return pairs === null ? '' : `${groupThousands(pairs)} hub pairs with routes`;
    }
    case 'travellers_and_bikes': {
      const travellers = count(counts, 'travellers');
      return travellers === null ? '' : `${groupThousands(travellers)} travellers`;
    }
    default:
      return '';
  }
}

export function keptLabel(basedNumber: number | null, planned: PlannedStep | undefined): string {
  return basedNumber !== null && planned?.causes.length === 0
    ? `kept from v${String(basedNumber)}`
    : 'kept: already computed with the same inputs';
}

export function routesProgressLine(
  progress: { readonly done: number; readonly total: number },
  queriesFailed: number,
): string {
  const queries = queriesFailed === 1 ? '1 query' : `${groupThousands(queriesFailed)} queries`;
  return `${groupThousands(progress.done)} of ${groupThousands(progress.total)} hub pairs · ${queries} gave no route so far`;
}

/** Reasons end without a full stop when a sentence follows them. */
export function failedStepLine(stepName: string, reason: string): string {
  return `${stepName} failed: ${reason.replace(/\.$/, '')}. Steps before it are kept.`;
}

export interface StepLine {
  /** "1 Area", or for the routes step while it runs "3 Routes — 12 of 48 hub pairs · ...". */
  readonly heading: string;
  readonly mark: '✓' | '●' | '✕' | null;
  readonly text: string;
  readonly tone: 'done' | 'running' | 'failed' | 'waiting';
  readonly progress: { readonly done: number; readonly total: number } | null;
}

export interface StepLineContext {
  /** The number of the version this one is based on; null when it is based on none. */
  readonly basedNumber: number | null;
  readonly plan: PlannedStep | undefined;
  /** Seconds the step has been running. */
  readonly elapsedS: number | null;
  /** The reason sentence of the step's failure. */
  readonly reason: string | null;
}

export function stepLine(step: RunStep, context: StepLineContext): StepLine {
  const name = STEP_NAMES[step.step];
  const title = `${String(step.number)} ${name}`;
  const counts = countsText(step);
  switch (step.state) {
    case 'done':
      return { heading: title, mark: '✓', text: counts, tone: 'done', progress: null };
    case 'kept': {
      const label = keptLabel(context.basedNumber, context.plan);
      const text = counts === '' ? label : `${label} · ${counts}`;
      return { heading: title, mark: '✓', text, tone: 'done', progress: null };
    }
    case 'running': {
      const progress = step.step === 'routes' ? step.progress : null;
      const failed = count(step.counts, 'queries_failed') ?? 0;
      return {
        heading: progress === null ? title : `${title} — ${routesProgressLine(progress, failed)}`,
        mark: '●',
        text: formatDuration(context.elapsedS ?? 0),
        tone: 'running',
        progress,
      };
    }
    case 'failed':
      return {
        heading: title,
        mark: '✕',
        text: failedStepLine(name, context.reason ?? ''),
        tone: 'failed',
        progress: null,
      };
    case 'cancelled':
      return { heading: title, mark: null, text: 'cancelled', tone: 'waiting', progress: null };
    default:
      return { heading: title, mark: null, text: 'waiting', tone: 'waiting', progress: null };
  }
}

// ---- the sentences of a build ---------------------------------------------------------------

export function buildingSentence(elapsedS: number, basedNumber: number | null): string {
  const building = `Building for ${formatDuration(elapsedS)}. It continues if you open another page`;
  return basedNumber === null
    ? `${building}.`
    : `${building}; v${String(basedNumber)} and its pricing versions stay available meanwhile.`;
}

export function queuedSentence(positionOrdinal: number, runName: string, kind: RunKind): string {
  const verb = kind === 'build' ? 'building' : 'running';
  return `Queued, ${ordinal(positionOrdinal)} in line: ${runName} is ${verb}. Runs go one at a time; this one starts when the run before it ends.`;
}

export function runnerSilentLine(time: string | null): string {
  const since = time === null ? '' : ` since ${time}`;
  return `The runner has not answered${since}. The run is kept and starts again when the runner is back (once).`;
}

export function queuedAgainLine(stepName: string, attempt: number): string {
  return `The runner stopped during ${stepName}. The run was queued again (${ordinal(attempt)} attempt): ${stepName} starts again from the beginning; steps before it are kept.`;
}

// ---- failures -------------------------------------------------------------------------------

export const FAILURE_REASONS: Readonly<Record<string, string>> = {
  trip_planner_unreachable: 'the trip planner did not answer',
  instance_unbalanced: "the model's package could not balance the bike options of this instance",
  stage_error: "an error stopped the step. The details are in the run's log.",
  killed: 'the process was stopped by the system; the machine may be out of memory',
  interrupted: 'the run was interrupted twice by a stop of the runner',
  timetable_mismatch: "the trip planner's timetable is not the city data's timetable",
  no_public_transport: '',
};

/** The reason sentence of a failure code; the stored reason for a code this screen does not know. */
export function failureReason(code: string, routingDate: string | null, stored: string): string {
  if (code === 'no_public_transport') {
    const date =
      routingDate === null ? 'the routing date' : `the routing date, ${longDate(routingDate)},`;
    return `the trip planner found no public transport route for any hub pair; ${date} may be outside the timetable (see City data)`;
  }
  return FAILURE_REASONS[code] ?? stored;
}

export function runAgainFromLabel(stepName: string): string {
  return `Run again from ${stepName}`;
}

export const RUN_AGAIN = 'Run again';
export const OPEN_LOG = "Open the run's log";

// ---- cancelling -----------------------------------------------------------------------------

export function cancelQuestion(name: string, queued: boolean, kind: RunKind = 'build'): string {
  const what = queued
    ? 'Cancel this run? Nothing has run yet.'
    : 'Cancel this run? The running step stops and is not stored; steps already done are kept.';
  const then = kind === 'build' ? 'edit it as a new version' : 'duplicate it';
  return `${what} ${name} stays in the menu as cancelled: you can run it again or ${then}.`;
}

export function cancelLabels(queued: boolean): {
  readonly open: string;
  readonly confirm: string;
  readonly keep: string;
} {
  return queued
    ? { open: 'Remove from the queue', confirm: 'Remove from the queue', keep: 'Keep' }
    : { open: 'Cancel run', confirm: 'Cancel the run', keep: 'Keep running' };
}

export function cancelledCard(stepName: string, finishedAt: Date): string {
  return `Run cancelled during ${stepName} on ${formatInstantDay(finishedAt)}. Steps before it are kept.`;
}

// ---- the run line of the menu ---------------------------------------------------------------

/** `name` is the subject as the menu writes it: "Geneva 3 km v2". */
export function runLineBuilding(
  name: string,
  elapsedS: number,
  queued: number,
  kind: RunKind = 'build',
): string {
  const verb = kind === 'build' ? 'building' : 'running';
  const waiting = queued > 0 ? ` · ${String(queued)} queued` : '';
  return `● ${name} ${verb} · ${formatDuration(elapsedS)}${waiting}`;
}

export function runLineSilent(name: string): string {
  return `● ${name} · the runner is not answering`;
}

export function runLineReady(name: string): string {
  return `✓ ${name}: ready`;
}

/** The subject of a run as the menu writes it: "Geneva 3 km v2"; the id for a subject the menu does not list. */
export function subjectName(
  run: Pick<Run, 'subject'>,
  entries: readonly InstanceMenuEntry[],
): string {
  if (run.subject.type === 'instance_version') {
    for (const entry of entries) {
      const version = entry.versions.find((candidate) => candidate.id === run.subject.id);
      if (version !== undefined) return `${entry.name} v${String(version.number)}`;
    }
  }
  if (run.subject.type === 'pricing_version') {
    // A pricing version's id is `{instance version}.{letter}`.
    for (const entry of entries) {
      const owner = entry.versions.find((candidate) =>
        run.subject.id.startsWith(`${candidate.id}.`),
      );
      if (owner !== undefined) return `Version ${run.subject.id.slice(owner.id.length + 1)}`;
    }
  }
  return run.subject.id;
}
