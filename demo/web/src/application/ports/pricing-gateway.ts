import type {
  HubPairResult,
  HubResult,
  PricingResult,
  StoredSimulation,
} from '../../domain/pricing-result';
import type { Comparison } from '../../domain/comparison';
import type { PricingChanges, PricingVersion } from '../../domain/pricing-version';

/** `refused`: the API did not queue the run (a rule is broken, a component is missing, a run is active). */
export type PricingRunQueued =
  | { readonly kind: 'queued'; readonly runId: string }
  | { readonly kind: 'refused'; readonly detail: string };

/** What deleting a sealed version answered: it is gone, or why it stays (`409 run_active`, `409 is_showcase`). */
export type PricingDeleted =
  { readonly kind: 'deleted' } | { readonly kind: 'run_active' } | { readonly kind: 'is_showcase' };

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
  /** Every stored simulation of the version, the current rule's and earlier ones; null without a version. */
  simulations(id: string): Promise<StoredSimulation[] | null>;
  /** The comparison of two to four finished versions of one instance version, for one period (the API's default when null). */
  compare(ids: readonly string[], period: string | null): Promise<Comparison>;
  /** Seals the draft and queues its pricing run. */
  run(id: string): Promise<PricingRunQueued>;
  /** Queues a simulation run (no solve) of the version's stored result with the current rule. */
  simulate(id: string): Promise<PricingRunQueued>;
  /** Deletes a version with its goals and result; `refused` kinds leave it in place. */
  remove(id: string): Promise<PricingDeleted>;
}
