import type { Run } from '../../domain/run';
import type { BuildQueued, CityInstanceGateway } from '../ports/city-instance-gateway';
import type { RunGateway } from '../ports/run-gateway';

interface Gateways {
  runs: RunGateway;
  cityInstances: CityInstanceGateway;
}

export function loadRun({ runs }: Pick<Gateways, 'runs'>, id: string): Promise<Run> {
  return runs.get(id);
}

/** The queued and running runs. */
export function loadActiveRuns({ runs }: Pick<Gateways, 'runs'>): Promise<Run[]> {
  return runs.listActive();
}

/** Asks for the run to stop: a queued run is removed at once, a running one at its next safe point. */
export function cancelRun({ runs }: Pick<Gateways, 'runs'>, id: string): Promise<Run> {
  return runs.cancel(id);
}

/** Queues the build of the version again: a failed or cancelled build keeps its finished steps. */
export function runAgain(
  { cityInstances }: Pick<Gateways, 'cityInstances'>,
  versionId: string,
): Promise<BuildQueued> {
  return cityInstances.build(versionId);
}
