import type { PricingChanges, PricingVersion } from '../../domain/pricing-version';
import type { PricingDeleted, PricingGateway, PricingRunQueued } from '../ports/pricing-gateway';

interface Gateways {
  pricing: PricingGateway;
}

/** "+ New pricing version": a draft on the built instance version, its goals the package's defaults. */
export function newPricingVersion(
  { pricing }: Gateways,
  instanceVersionId: string,
): Promise<PricingVersion> {
  return pricing.create(instanceVersionId);
}

/** "Duplicate": a draft on the same instance version with the goals of `version`. */
export function duplicatePricingVersion(
  { pricing }: Gateways,
  version: Pick<PricingVersion, 'id' | 'instanceVersionId'>,
): Promise<PricingVersion> {
  return pricing.create(version.instanceVersionId, version.id);
}

export function savePricingDraft(
  { pricing }: Gateways,
  id: string,
  changes: PricingChanges,
): Promise<PricingVersion> {
  return pricing.patch(id, changes);
}

export function discardPricingDraft({ pricing }: Gateways, id: string): Promise<void> {
  return pricing.discard(id);
}

/** Waits for the pending autosave, then seals the draft as saved and queues its pricing run. */
export async function runPricingVersion(
  { pricing }: Gateways,
  id: string,
  flushAutosave: () => Promise<void>,
): Promise<PricingRunQueued> {
  await flushAutosave();
  return pricing.run(id);
}

/** "Simulate again with v{new}": a simulation run of the stored result; no pricing model run. */
export function simulatePricingVersion(
  { pricing }: Gateways,
  id: string,
): Promise<PricingRunQueued> {
  return pricing.simulate(id);
}

/** "Delete Version {letter}": a version with a result, a failure or a cancellation. */
export function deletePricingVersion({ pricing }: Gateways, id: string): Promise<PricingDeleted> {
  return pricing.remove(id);
}
