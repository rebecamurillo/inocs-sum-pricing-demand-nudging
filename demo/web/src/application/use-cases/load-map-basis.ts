import type { CityDataset } from '../../domain/map';
import { latestDataset } from '../../domain/map';
import type { BasemapGateway } from '../ports/basemap-gateway';
import type { CityDatasetGateway } from '../ports/city-dataset-gateway';

export interface MapBasis {
  readonly dataset: CityDataset;
  /** The PMTiles file to draw, or null when it is not served: the map is then the ground colour. */
  readonly basemapUrl: string | null;
}

/** The data set the map shows (the named one, else the most recent) and its basemap file. */
export async function loadMapBasis(
  gateways: { cityDatasets: CityDatasetGateway; basemap: BasemapGateway },
  datasetId: string | null,
): Promise<MapBasis | null> {
  const datasets = await gateways.cityDatasets.list();
  const dataset =
    datasetId === null
      ? latestDataset(datasets)
      : (datasets.find((candidate) => candidate.id === datasetId) ?? null);
  if (dataset === null) return null;
  const present = await gateways.basemap.exists(dataset.id);
  return { dataset, basemapUrl: present ? gateways.basemap.url(dataset.id) : null };
}
