import type { Run } from '../../domain/run';

export interface RunGateway {
  /** One run with its steps and the state of its runner. */
  get(id: string): Promise<Run>;
  /** The queued and running runs, the running one first. */
  listActive(): Promise<Run[]>;
  /** Asks the run to stop: at once when queued, at its next safe point when running. */
  cancel(id: string): Promise<Run>;
}
