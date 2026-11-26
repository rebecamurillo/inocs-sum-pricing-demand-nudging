import type { LayoutPreferences } from './layout-preferences';
import type { SystemStatusGateway } from './system-status-gateway';

/** Every gateway the presentation layer can reach; one field per port. */
export interface Gateways {
  readonly systemStatus: SystemStatusGateway;
  readonly layoutPreferences: LayoutPreferences;
}
