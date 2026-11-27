/** A run as the Lab reads it: a build of an instance version (or, later, a pricing run). */
import type { StepName } from './city-instance';

export type RunKind = 'build' | 'pricing' | 'simulation';
export type RunState = 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled';
export type RunStepState = 'pending' | 'running' | 'done' | 'kept' | 'failed' | 'cancelled';

export interface RunStep {
  readonly step: StepName;
  /** 1 to 4 for a build. */
  readonly number: number;
  readonly state: RunStepState;
  readonly startedAt: Date | null;
  readonly finishedAt: Date | null;
  /** What the step counted, as the API names it (`stops`, `hubs`, `hub_pairs_with_routes`, ...). */
  readonly counts: Readonly<Record<string, unknown>>;
  /** Pairs routed out of the pairs to route, while the routes step runs. */
  readonly progress: { readonly done: number; readonly total: number } | null;
}

export interface RunFailure {
  readonly step: string | null;
  readonly code: string;
  readonly reason: string;
}

export interface Run {
  readonly id: string;
  readonly kind: RunKind;
  readonly subject: { readonly type: 'instance_version' | 'pricing_version'; readonly id: string };
  readonly state: RunState;
  /** 1 for the first try; 2 for a run queued again after a stop of the runner. */
  readonly attempt: number;
  readonly queuedAt: Date;
  readonly startedAt: Date | null;
  readonly finishedAt: Date | null;
  /** The API's clock when it answered. */
  readonly serverTime: Date;
  /** 1-based among the queued runs; null for a run that is not queued. */
  readonly queuePosition: number | null;
  readonly runner: { readonly alive: boolean; readonly lastHeartbeatAt: Date | null };
  readonly steps: readonly RunStep[];
  readonly failure: RunFailure | null;
}

export const ACTIVE_STATES: readonly RunState[] = ['queued', 'running'];

export function isActive(run: Run): boolean {
  return ACTIVE_STATES.includes(run.state);
}
