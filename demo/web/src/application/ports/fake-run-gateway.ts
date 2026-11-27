import { isActive, type Run, type RunStep } from '../../domain/run';
import type { RunGateway } from './run-gateway';

const AT = new Date('2026-11-27T10:00:00Z');

export function sampleStep(
  overrides: Partial<RunStep> & Pick<RunStep, 'step' | 'number'>,
): RunStep {
  return {
    state: 'pending',
    startedAt: null,
    finishedAt: null,
    counts: {},
    progress: null,
    lastDurationS: null,
    ...overrides,
  };
}

/** The four steps of a build, `done` up to the one at `running` (1 to 4), `pending` after it. */
export function sampleBuildSteps(running: number): RunStep[] {
  const names = ['area', 'hubs', 'routes', 'travellers_and_bikes'] as const;
  const counts = [
    { stops: 30, bike_stations: 12 },
    { hubs: 6 },
    { hub_pairs_with_routes: 24, queries: 48, queries_failed: 0 },
    { travellers: 1000 },
  ];
  return names.map((step, at) => {
    const number = at + 1;
    if (number < running) {
      return sampleStep({ step, number, state: 'done', counts: counts[at] ?? {}, startedAt: AT });
    }
    if (number === running) {
      return sampleStep({
        step,
        number,
        state: 'running',
        startedAt: new Date(AT.getTime() + 60_000),
        progress: step === 'routes' ? { done: 12, total: 48 } : null,
        counts: step === 'routes' ? { queries_failed: 2 } : {},
      });
    }
    return sampleStep({ step, number });
  });
}

/** A build of `geneva-3km.v2` running its routes step, 4 min 12 s after it started. */
export const sampleRunningBuild: Run = {
  id: 'run-2',
  kind: 'build',
  subject: { type: 'instance_version', id: 'geneva-3km.v2' },
  state: 'running',
  attempt: 1,
  queuedAt: AT,
  startedAt: AT,
  finishedAt: null,
  serverTime: new Date(AT.getTime() + 252_000),
  queuePosition: null,
  runner: { alive: true, lastHeartbeatAt: new Date(AT.getTime() + 250_000) },
  steps: sampleBuildSteps(3),
  failure: null,
};

/** A fake of the run gateway over runs held in memory; it records the calls it gets. */
export interface FakeRunGateway extends RunGateway {
  readonly calls: string[];
  /** Adds the run, or replaces the one with its id. */
  put(run: Run): void;
}

export function fakeRunGateway(initial: readonly Run[] = []): FakeRunGateway {
  const runs = new Map(initial.map((run) => [run.id, run]));
  const calls: string[] = [];
  return {
    calls,
    put: (run) => {
      runs.set(run.id, run);
    },
    get: (id) => {
      calls.push(`get ${id}`);
      const found = runs.get(id);
      return found === undefined
        ? Promise.reject(new Error(`No run ${id}.`))
        : Promise.resolve(found);
    },
    listActive: () => {
      calls.push('listActive');
      const active = [...runs.values()].filter(isActive);
      const order = (run: Run) => run.queuePosition ?? 0;
      return Promise.resolve(active.sort((a, b) => order(a) - order(b)));
    },
    cancel: (id) => {
      calls.push(`cancel ${id}`);
      const found = runs.get(id);
      if (found === undefined) return Promise.reject(new Error(`No run ${id}.`));
      // A queued run is removed at once; a running one stops at its next safe point.
      const answer: Run =
        found.state === 'queued'
          ? { ...found, state: 'cancelled', queuePosition: null, finishedAt: found.serverTime }
          : found;
      runs.set(id, answer);
      return Promise.resolve(answer);
    },
  };
}
