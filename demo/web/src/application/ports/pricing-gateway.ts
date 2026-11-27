import type { HubPairResult, HubResult, PricingResult } from '../../domain/pricing-result';
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
  /** Starts a draft on a built instance version; with `basedOn`, a copy of that version's goals. */
  create(instanceVersionId: string, basedOn?: string): Promise<PricingVersion>;
  /** Stores the goals (and the name) as sent; the answer carries every rule result. */
  patch(id: string, changes: PricingChanges): Promise<PricingVersion>;
  /** Removes a draft. */
  discard(id: string): Promise<void>;
  /** The stored result of a version; null when it has none (the API's 404 `no_result`). */
  result(id: string): Promise<PricingResult | null>;
  /** The model's price and flow per hub pair; null when the version has no result. */
  hubPairResults(id: string): Promise<HubPairResult[] | null>;
  /** The model's bike rides and mean price per hub; null when the version has no result. */
  hubResults(id: string): Promise<HubResult[] | null>;
  /** Seals the draft and queues its pricing run. */
  run(id: string): Promise<PricingRunQueued>;
}
