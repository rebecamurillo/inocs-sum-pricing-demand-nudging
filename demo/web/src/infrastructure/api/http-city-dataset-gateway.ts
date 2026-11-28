import { ApiProblemError } from '../../application/errors';
import type { CityDatasetGateway } from '../../application/ports/city-dataset-gateway';
import type { CityDataset, GeoBounds } from '../../domain/map';
import type { components } from './generated/schema';

type CityDatasetListResponse = components['schemas']['CityDatasetList'];
type CityDatasetResponse = components['schemas']['CityDatasetResource'];

const cityDatasetsPath = '/api/v1/city-datasets';

function boundsOf(ring: readonly (readonly number[])[]): GeoBounds {
  const lons = ring.map((position) => position[0] ?? 0);
  const lats = ring.map((position) => position[1] ?? 0);
  return [Math.min(...lons), Math.min(...lats), Math.max(...lons), Math.max(...lats)];
}

function toCityDataset(response: CityDatasetResponse): CityDataset {
  return {
    id: response.id,
    centre: { lat: response.preset.centre_lat, lon: response.preset.centre_lon },
    radiusM: response.preset.radius_m,
    availableArea: boundsOf(response.available_area.coordinates[0] ?? []),
  };
}

export class HttpCityDatasetGateway implements CityDatasetGateway {
  private readonly fetchImpl: typeof fetch;

  constructor(fetchImpl: typeof fetch) {
    this.fetchImpl = fetchImpl;
  }

  async list(): Promise<CityDataset[]> {
    let response: Response;
    try {
      response = await this.fetchImpl(cityDatasetsPath, {
        headers: { Accept: 'application/json' },
      });
    } catch (cause) {
      throw new ApiProblemError({
        code: 'api_unreachable',
        title: 'The API could not be reached',
        detail: cause instanceof Error ? cause.message : String(cause),
      });
    }
    if (!response.ok) {
      throw new ApiProblemError({
        code: 'unexpected_response',
        title: `The API answered with status ${String(response.status)}`,
        detail: 'The city data sets could not be read.',
      });
    }
    let body: CityDatasetListResponse;
    try {
      body = (await response.json()) as CityDatasetListResponse;
    } catch {
      throw new ApiProblemError({
        code: 'unexpected_response',
        title: 'The API answer could not be read',
        detail: 'The answer is not JSON.',
      });
    }
    return body.items.map(toCityDataset);
  }
}
