import type { PricingChanges, PricingVersion } from '../../domain/pricing-version';

/** `refused`: the API did not queue the run (a rule is broken, a component is missing, a run is active). */
export type PricingRunQueued =
  | { readonly kind: 'queued'; readonly runId: string }
  | { readonly kind: 'refused'; readonly detail: string };

export interface PricingGateway {
  /** The pricing versions of an instance version, in letter order. */
  list(instanceVersionId: string): Promise<PricingVersion[]>;
  /** One pricing version; null when the API has none by this id. */
  get(id: string): Promise<PricingVersion | null>;
  /** Starts a draft on a built instance version. */
  create(instanceVersionId: string): Promise<PricingVersion>;
  /** Stores the goals (and the name) as sent; the answer carries every rule result. */
  patch(id: string, changes: PricingChanges): Promise<PricingVersion>;
  /** Removes a draft. */
  discard(id: string): Promise<void>;
  /** Seals the draft and queues its pricing run. */
  run(id: string): Promise<PricingRunQueued>;
}
