import { describe, expect, it } from 'vitest';
import { l5Layers, L5_IDS } from './l5-layers';

const declaration = l5Layers({
  centre: { lat: 46.2, lon: 6.14 },
  radiusM: 3000,
  stations: [
    { id: 'p1', kind: 'pt', lat: 46.21, lon: 6.14 },
    { id: 'b1', kind: 'bs', lat: 46.2, lon: 6.15 },
  ],
  hubs: [
    {
      id: 'H1',
      lat: 46.2,
      lon: 6.14,
      outline: [
        [6.1, 46.1],
        [6.2, 46.1],
        [6.2, 46.2],
        [6.1, 46.1],
      ],
    },
    { id: 'H2', lat: 46.22, lon: 6.16, outline: null },
  ],
});

const features = (id: string) => {
  const source = declaration.sources[id];
  if (source?.type !== 'geojson') throw new Error(`no geojson source ${id}`);
  return source.data.features;
};

describe('l5Layers', () => {
  it('draws the study circle, the hub outlines and the bike stations in the identity colours', () => {
    const byId = (id: string) => declaration.layers.find((layer) => layer.id === id);
    expect(declaration.layers.map((layer) => layer.id)).toEqual([
      L5_IDS.studyCircle,
      L5_IDS.hubOutlines,
      L5_IDS.bikeStations,
    ]);
    expect(byId(L5_IDS.studyCircle)?.paint['fill-color']).toBe('#b7bcb5');
    expect(byId(L5_IDS.hubOutlines)?.paint).toMatchObject({
      'line-color': '#949c93',
      'line-dasharray': [2, 2],
    });
    expect(byId(L5_IDS.bikeStations)?.paint).toMatchObject({
      'circle-color': '#98c33a',
      'circle-stroke-color': '#54740f',
    });
  });

  it('holds only the hubs with an outline and only the bike stations', () => {
    expect(features(L5_IDS.hubOutlines)).toHaveLength(1);
    expect(features(L5_IDS.bikeStations)).toHaveLength(1);
    expect(features(L5_IDS.bikeStations)[0]?.properties).toEqual({ id: 'b1' });
  });
});
