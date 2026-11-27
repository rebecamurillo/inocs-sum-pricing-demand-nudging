import type { InstanceVersion } from '../../domain/city-instance';
import { parametersAsWire } from '../../domain/draft-text';
import type {
  BuildQueued,
  CityInstanceGateway,
  CreatedDraft,
  CreatedInstance,
  ParameterChanges,
  StartFrom,
} from '../ports/city-instance-gateway';

interface Gateways {
  cityInstances: CityInstanceGateway;
}

/** Creates an instance and its first draft from the data set; the name is trimmed. */
export function createInstance(
  { cityInstances }: Gateways,
  name: string,
  datasetId: string,
  startFrom: StartFrom,
): Promise<CreatedInstance> {
  return cityInstances.createInstance(name.trim(), datasetId, startFrom);
}

/** "Edit as a new version": the draft based on this version, or the draft the instance has. */
export function editAsNewVersion(
  { cityInstances }: Gateways,
  instanceId: string,
  basedOnId: string,
): Promise<CreatedDraft> {
  return cityInstances.createDraft(instanceId, basedOnId);
}

export function saveDraft(
  { cityInstances }: Gateways,
  draftId: string,
  changes: ParameterChanges,
): Promise<InstanceVersion> {
  return cityInstances.patch(draftId, changes);
}

/** Sets every parameter of the draft to the package's defaults; the draft's name, data set and versions stay. */
export function restoreDefaults(
  gateways: Gateways,
  draft: InstanceVersion,
): Promise<InstanceVersion> {
  if (draft.packageDefaults === null) {
    return Promise.reject(new Error('The package defaults are not known for this draft.'));
  }
  return saveDraft(gateways, draft.id, parametersAsWire(draft.packageDefaults));
}

/** Sets every parameter of the draft to the package's defaults or to those of a saved version. */
export async function startFrom(
  gateways: Gateways,
  draft: InstanceVersion,
  source: StartFrom,
): Promise<InstanceVersion> {
  if (source.kind === 'package_defaults') return restoreDefaults(gateways, draft);
  const version = await gateways.cityInstances.version(source.versionId);
  if (version === null) {
    throw new Error(`The version ${source.versionId} to start from could not be found.`);
  }
  return saveDraft(gateways, draft.id, parametersAsWire(version.parameters));
}

export function discardDraft({ cityInstances }: Gateways, draftId: string): Promise<void> {
  return cityInstances.discard(draftId);
}

/** Waits for the pending autosave, then queues the build of the draft as saved. */
export async function saveAndBuild(
  { cityInstances }: Gateways,
  draftId: string,
  flushAutosave: () => Promise<void>,
): Promise<BuildQueued> {
  await flushAutosave();
  return cityInstances.build(draftId);
}

/** The draft "Edit as a new version" opens: a new one, or the one the instance already has. */
export interface OpenedDraft {
  readonly version: InstanceVersion;
  /** True when the instance had a draft already. */
  readonly existed: boolean;
}

export async function openDraft(
  gateways: Gateways,
  instanceId: string,
  basedOnId: string,
): Promise<OpenedDraft> {
  const result = await editAsNewVersion(gateways, instanceId, basedOnId);
  if (result.kind === 'created') return { version: result.version, existed: false };
  const existing = await gateways.cityInstances.version(result.draftId);
  if (existing === null) throw new Error(`The draft ${result.draftId} could not be found.`);
  return { version: existing, existed: true };
}
