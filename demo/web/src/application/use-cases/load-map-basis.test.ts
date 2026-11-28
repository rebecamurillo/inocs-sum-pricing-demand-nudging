import { describe, expect, it, vi } from 'vitest';
import type { CityDataset } from '../../domain/map';
import { loadMapBasis } from './load-map-basis';

const make = (id: string): CityDataset => ({
  id,
  centre: { lat: 46.2, lon: 6.14 },
  radiusM: 3000,
  availableArea: [6, 46, 6.3, 46.4],
});

function gateways(datasets: CityDataset[], served: string[]) {
  return {
    cityDatasets: { list: () => Promise.resolve(datasets) },
    basemap: {
      exists: vi.fn((id: string) => Promise.resolve(served.includes(id))),
      url: (id: string) => `/basemap/${id}.pmtiles`,
    },
  };
}

describe('loadMapBasis', () => {
  it('takes the most recent data set and its file when none is named', async () => {
    const basis = await loadMapBasis(gateways([make('a'), make('b')], ['b']), null);

    expect(basis).toEqual({ dataset: make('b'), basemapUrl: '/basemap/b.pmtiles' });
  });

  it('takes the named data set', async () => {
    const basis = await loadMapBasis(gateways([make('a'), make('b')], ['a']), 'a');

    expect(basis?.dataset.id).toBe('a');
    expect(basis?.basemapUrl).toBe('/basemap/a.pmtiles');
  });

  it('has no file url when the file is not served', async () => {
    expect(await loadMapBasis(gateways([make('a')], []), null)).toEqual({
      dataset: make('a'),
      basemapUrl: null,
    });
  });

  it('is null with no data set, and does not ask for a file', async () => {
    const rig = gateways([], []);

    expect(await loadMapBasis(rig, null)).toBeNull();
    expect(rig.basemap.exists).not.toHaveBeenCalled();
  });

  it('is null for a named data set that does not exist', async () => {
    expect(await loadMapBasis(gateways([make('a')], ['a']), 'zz')).toBeNull();
  });
});
