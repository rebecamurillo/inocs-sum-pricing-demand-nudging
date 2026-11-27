import type { Showcase } from '../../domain/showcase';
import type { PricingGateway } from '../ports/pricing-gateway';

/** The result marked for the home page; null when none is marked. */
export function loadShowcase(gateway: PricingGateway): Promise<Showcase | null> {
  return gateway.getShowcase();
}
