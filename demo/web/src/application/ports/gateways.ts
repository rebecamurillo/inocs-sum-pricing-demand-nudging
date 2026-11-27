import type { BasemapGateway } from './basemap-gateway';
import type { CityInstanceGateway } from './city-instance-gateway';
import type { CityDatasetGateway } from './city-dataset-gateway';
import type { LayoutPreferences } from './layout-preferences';
import type { PricingGateway } from './pricing-gateway';
import type { RunGateway } from './run-gateway';
import type { SystemStatusGateway } from './system-status-gateway';
import type { TripGateway } from './trip-gateway';

/** Every gateway the presentation layer can reach; one field per port. */
export interface Gateways {
  readonly systemStatus: SystemStatusGateway;
  readonly layoutPreferences: LayoutPreferences;
  readonly cityDatasets: CityDatasetGateway;
  readonly basemap: BasemapGateway;
  readonly cityInstances: CityInstanceGateway;
  readonly runs: RunGateway;
  readonly pricing: PricingGateway;
  readonly trips: TripGateway;
}
