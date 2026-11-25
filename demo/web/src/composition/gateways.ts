import type { Gateways } from '../application/ports/gateways';
import { browserFetch } from '../infrastructure/api/browser-fetch';
import { HttpSystemStatusGateway } from '../infrastructure/api/http-system-status-gateway';

export function createGateways(): Gateways {
  // The adapters call the API on their own origin under /api; no address is configured.
  return { systemStatus: new HttpSystemStatusGateway(browserFetch) };
}
