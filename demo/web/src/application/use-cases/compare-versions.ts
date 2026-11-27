import type { Comparison } from '../../domain/comparison';
import { pricingVersionId } from '../../domain/pricing-version';
import type { PricingGateway } from '../ports/pricing-gateway';

interface Gateways {
  pricing: PricingGateway;
}

/** The comparison of the versions named by their letters in one instance version. */
export function compareVersions(
  { pricing }: Gateways,
  instanceVersionId: string,
  letters: readonly string[],
  period: string | null,
): Promise<Comparison> {
  return pricing.compare(
    letters.map((letter) => pricingVersionId(instanceVersionId, letter)),
    period,
  );
}
