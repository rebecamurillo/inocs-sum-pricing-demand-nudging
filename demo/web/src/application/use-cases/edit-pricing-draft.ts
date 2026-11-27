import type { PricingChanges, PricingVersion } from '../../domain/pricing-version';
import type { PricingGateway, PricingRunQueued } from '../ports/pricing-gateway';

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
