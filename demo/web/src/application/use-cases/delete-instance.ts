import type { CityInstanceGateway, Deleted } from '../ports/city-instance-gateway';

interface Gateways {
  cityInstances: CityInstanceGateway;
}

/** Deletes one instance version; `run_active` when a run of it is queued or running. */
export function deleteVersion({ cityInstances }: Gateways, versionId: string): Promise<Deleted> {
  return cityInstances.deleteVersion(versionId);
}

/** Deletes an instance with all its versions; `run_active` when a run of any is queued or running. */
export function deleteInstance({ cityInstances }: Gateways, instanceId: string): Promise<Deleted> {
  return cityInstances.deleteInstance(instanceId);
}
