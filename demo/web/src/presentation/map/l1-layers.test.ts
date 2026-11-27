import { describe, expect, it } from 'vitest';
import { l1Layers, L1_IDS } from './l1-layers';

const input = {
  centre: { lat: 46.2, lon: 6.14 },
  radiusM: 3000,
  stations: [
    { id: 'p1', kind: 'pt', lat: 46.21, lon: 6.14 },
    { id: 'b1', kind: 'bs', lat: 46.2, lon: 6.15 },
    { id: 'b2', kind: 'bs', lat: 46.19, lon: 6.13 },
  ],
  hubs: [
    {
      id: 'h1',
      lat: 46.2,
      lon: 6.14,
      outline: [
        [6.1, 46.1],
        [6.2, 46.1],
        [6.2, 46.2],
        [6.1, 46.1],
      ],
    },
    { id: 'h2', lat: 46.22, lon: 6.16, outline: null },
  ],
  hubPairs: [
    { originHub: 'h1', destinationHub: 'h2' },
    { originHub: 'h2', destinationHub: 'ghost' },
    { originHub: 'ghost', destinationHub: 'h1' },
  ],
} as const;

function features(id: string) {
  const source = l1Layers(input).sources[id];
  if (source?.type !== 'geojson') throw new Error(`no geojson source ${id}`);
  return source.data.features;
}

describe('l1Layers', () => {
  it('returns the five groups in the identity colours, none a symbol', () => {
    const { layers } = l1Layers(input);
    const byId = (id: string) => layers.find((layer) => layer.id === id);

    expect(layers.map((layer) => layer.id)).toEqual([
      'l1-study-circle',
      'l1-hub-pairs',
      'l1-hub-outlines',
      'l1-stops',
      'l1-bike-stations',
    ]);
    expect(layers.some((layer) => (layer.type as string) === 'symbol')).toBe(false);
    expect(byId(L1_IDS.studyCircle)).toMatchObject({
      type: 'fill',
      paint: { 'fill-color': '#b7bcb5' },
    });
    expect(byId(L1_IDS.stops)).toMatchObject({
      type: 'circle',
      paint: { 'circle-color': '#004494' },
    });
    expect(byId(L1_IDS.bikeStations)).toMatchObject({
      type: 'circle',
      paint: { 'circle-color': '#98c33a', 'circle-stroke-color': '#54740f' },
    });
    expect(byId(L1_IDS.hubOutlines)).toMatchObject({
      type: 'line',
      paint: { 'line-color': '#949c93', 'line-dasharray': [2, 2] },
    });
    expect(byId(L1_IDS.hubPairs)).toMatchObject({ type: 'line' });
  });

  it('reads every layer from a source of the same declaration', () => {
    const { layers, sources } = l1Layers(input);

    for (const layer of layers) expect(Object.keys(sources)).toContain(layer.source);
  });

  it('draws the study circle as one closed ring', () => {
    const [circle] = features(L1_IDS.studyCircle);

    expect(circle?.geometry.type).toBe('Polygon');
    const ring = (circle?.geometry.coordinates as number[][][])[0] ?? [];
    expect(ring[0]).toEqual(ring.at(-1));
  });

  it('splits the stations into stops and bike stations', () => {
    expect(features(L1_IDS.stops).map((f) => f.properties.id)).toEqual(['p1']);
    expect(features(L1_IDS.bikeStations).map((f) => f.properties.id)).toEqual(['b1', 'b2']);
    expect(features(L1_IDS.stops)[0]?.geometry.coordinates).toEqual([6.14, 46.21]);
  });

  it('draws only the hubs that have an outline', () => {
    expect(features(L1_IDS.hubOutlines).map((f) => f.properties.id)).toEqual(['h1']);
  });

  it('joins the two hubs centres per pair and skips a pair with an unknown hub', () => {
    const lines = features(L1_IDS.hubPairs);

    expect(lines).toHaveLength(1);
    expect(lines[0]?.geometry).toEqual({
      type: 'LineString',
      coordinates: [
        [6.14, 46.2],
        [6.16, 46.22],
      ],
    });
  });

  it('declares empty sources for an instance without stations, hubs and pairs', () => {
    const empty = l1Layers({ ...input, stations: [], hubs: [], hubPairs: [] });

    expect(empty.layers).toHaveLength(5);
    expect(
      Object.values(empty.sources).filter(
        (source) => source.type === 'geojson' && source.data.features.length === 0,
      ),
    ).toHaveLength(4);
  });
});
