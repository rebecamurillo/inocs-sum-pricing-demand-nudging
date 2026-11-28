import { describe, expect, it } from 'vitest';
import type { MapHub } from '../../domain/map';
import { L4_IDS, l4Layers } from './l4-layers';

const ring = [
  [6.1, 46.2],
  [6.11, 46.2],
  [6.11, 46.21],
  [6.1, 46.2],
] as const;
const hub = (id: string, lon: number, outline: MapHub['outline'] = null): MapHub => ({
  id,
  lat: 46.2,
  lon,
  outline,
});
const hubs = [hub('h1', 6.1, ring), hub('h2', 6.2), hub('h3', 6.3), hub('h4', 6.4)];
const base = { centre: { lat: 46.2, lon: 6.14 }, radiusM: 3000, hubs, dimmed: false };

function discs(values: ReadonlyMap<string, number>) {
  const source = l4Layers({ ...base, values }).sources[L4_IDS.hubDiscs];
  if (source?.type !== 'geojson') throw new Error('no discs');
  return source.data.features.map((feature) => feature.properties);
}

describe('l4Layers', () => {
  it('draws the study circle, the hub outlines and the discs, in that order', () => {
    const { layers, sources } = l4Layers({ ...base, values: new Map([['h1', 1]]) });
    expect(layers.map((layer) => layer.id)).toEqual([
      'l4-study-circle',
      'l4-hub-outlines',
      'l4-hub-discs',
    ]);
    expect(layers.map((layer) => layer.type)).toEqual(['fill', 'line', 'circle']);
    const outlines = sources[L4_IDS.hubOutlines];
    expect(outlines?.type === 'geojson' && outlines.data.features).toHaveLength(1);
  });

  it('draws one disc per hub that has a value, coloured and sized at minus m, 0 and plus m', () => {
    expect(
      discs(
        new Map([
          ['h1', -0.4],
          ['h2', 0],
          ['h3', 0.4],
        ]),
      ),
    ).toEqual([
      { id: 'h1', value: -0.4, colour: '#b4530a', radius: 28 },
      { id: 'h2', value: 0, colour: '#c9cdc8', radius: 10 },
      { id: 'h3', value: 0.4, colour: '#00336e', radius: 28 },
    ]);
  });

  it('leaves out a hub without a value and a value without a hub on the map', () => {
    const found = discs(
      new Map([
        ['h2', 0.2],
        ['unknown', 0.9],
      ]),
    );
    expect(found.map((item) => item.id)).toEqual(['h2']);
  });

  it('draws every disc as no change at 10 px when every value is 0, and none when there is none', () => {
    expect(
      discs(
        new Map([
          ['h1', 0],
          ['h2', 0],
        ]),
      ),
    ).toEqual([
      { id: 'h1', value: 0, colour: '#c9cdc8', radius: 10 },
      { id: 'h2', value: 0, colour: '#c9cdc8', radius: 10 },
    ]);
    expect(discs(new Map())).toEqual([]);
  });

  it('reads colour and radius from each disc, with a white ring, and steps back when dimmed', () => {
    const paint = (dimmed: boolean) =>
      l4Layers({ ...base, values: new Map([['h1', 1]]), dimmed }).layers[2]?.paint;
    expect(paint(false)).toMatchObject({
      'circle-radius': ['get', 'radius'],
      'circle-color': ['get', 'colour'],
      'circle-stroke-color': '#ffffff',
      'circle-opacity': 1,
    });
    expect(paint(true)).toMatchObject({ 'circle-opacity': 0.35 });
  });
});
