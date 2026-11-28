import type { PricingGateway } from '../ports/pricing-gateway';

/** Makes a finished version's result, for one period, the home page's showcase. */
export function setShowcase(
  gateway: PricingGateway,
  pricingVersionId: string,
  periodId: string,
): Promise<void> {
  return gateway.setShowcase(pricingVersionId, periodId);
}
