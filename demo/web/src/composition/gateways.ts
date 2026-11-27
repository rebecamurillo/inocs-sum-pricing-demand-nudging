import type { Gateways } from '../application/ports/gateways';
import { browserFetch } from '../infrastructure/api/browser-fetch';
import { HttpBasemapGateway } from '../infrastructure/api/http-basemap-gateway';
import { HttpCityDatasetGateway } from '../infrastructure/api/http-city-dataset-gateway';
import { HttpCityInstanceGateway } from '../infrastructure/api/http-city-instance-gateway';
import { HttpRunGateway } from '../infrastructure/api/http-run-gateway';
import { HttpSystemStatusGateway } from '../infrastructure/api/http-system-status-gateway';
import { LocalStorageLayoutPreferences } from '../infrastructure/storage/local-storage-layout-preferences';

/** Reading `window.localStorage` itself throws when the browser blocks site storage. */
function browserStorage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function createGateways(): Gateways {
  // The adapters call the API on their own origin under /api; no address is configured.
  return {
    systemStatus: new HttpSystemStatusGateway(browserFetch),
    layoutPreferences: new LocalStorageLayoutPreferences(browserStorage()),
    cityDatasets: new HttpCityDatasetGateway(browserFetch),
    basemap: new HttpBasemapGateway(browserFetch),
    cityInstances: new HttpCityInstanceGateway(browserFetch),
    runs: new HttpRunGateway(browserFetch),
  };
}
