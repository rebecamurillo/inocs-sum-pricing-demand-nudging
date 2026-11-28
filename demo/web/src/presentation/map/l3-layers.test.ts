import { describe, expect, it } from 'vitest';
import type { HubResult, ResultNumber } from '../../domain/pricing-result';
import { L3_IDS, l3Layers, pairLineLayer } from './l3-layers';

const num = (value: number): ResultNumber => ({
  value,
  unit: 'bike_rides',
  source: 'derived',
  group: 'advanced',
});

const hub = (id: string, lon: number, starting: number, ending: number, mean: number | null) =>
  ({
    hubId: id,
    label: id,
    lat: 46.2,
    lon,
    ridesStarting: num(starting),
    ridesEnding: num(ending),
    meanBikePrice: mean === null ? null : num(mean),
  }) satisfies HubResult;

const hubs = [hub('h1', 6.1, 40, 5, 1.2), hub('h2', 6.2, 10, 20, null), hub('h3', 6.3, 0, 0, 0.6)];
const base = { centre: { lat: 46.2, lon: 6.14 }, radiusM: 3000, hubs, dimmed: false };

function discs(measure: 'ridesStarting' | 'ridesEnding' | 'meanPrice') {
  const source = l3Layers({ ...base, measure }).sources[L3_IDS.hubDiscs];
  if (source?.type !== 'geojson') throw new Error('no discs');
  return source.data.features.map((feature) => feature.properties);
}

describe('l3Layers', () => {
  it('draws the study circle and one disc layer, in that order, with no pair line', () => {
    const { layers, sources } = l3Layers({ ...base, measure: 'ridesStarting' });
    expect(layers.map((layer) => layer.id)).toEqual(['l3-study-circle', 'l3-hub-discs']);
    expect(layers.map((layer) => layer.type)).toEqual(['fill', 'circle']);
    expect(Object.keys(sources)).toEqual(['l3-study-circle', 'l3-hub-discs']);
    expect(layers.some((layer) => layer.type === 'line')).toBe(false);
  });

  it('colours the discs on the green ramp with a white ring, size and colour from t', () => {
    const disc = l3Layers({ ...base, measure: 'ridesStarting' }).layers[1];
    expect(disc?.paint).toMatchObject({
      'circle-radius': ['interpolate', ['linear'], ['get', 't'], 0, 3, 1, 14],
      'circle-color': ['interpolate', ['linear'], ['get', 't'], 0, '#e3f1e1', 1, '#005a00'],
      'circle-stroke-color': '#ffffff',
      'circle-stroke-width': 1.5,
      'circle-opacity': 1,
    });
  });

  it('takes t as the value over the largest value of the measure', () => {
    expect(discs('ridesStarting')).toEqual([
      { id: 'h1', value: 40, t: 1 },
      { id: 'h2', value: 10, t: 0.25 },
      { id: 'h3', value: 0, t: 0 },
    ]);
    expect(discs('ridesEnding').map((item) => item.t)).toEqual([0.25, 1, 0]);
  });

  it('leaves a hub without a mean price out of that measure', () => {
    expect(discs('meanPrice')).toEqual([
      { id: 'h1', value: 1.2, t: 1 },
      { id: 'h3', value: 0.6, t: 0.5 },
    ]);
  });

  it('gives every disc t 0 when the largest value is 0', () => {
    const zero = l3Layers({ ...base, hubs: [hub('a', 6.1, 0, 0, null)], measure: 'ridesEnding' });
    const source = zero.sources[L3_IDS.hubDiscs];
    expect(source?.type === 'geojson' && source.data.features[0]?.properties).toEqual({
      id: 'a',
      value: 0,
      t: 0,
    });
  });

  it('dims the discs when a pair is shown', () => {
    const disc = l3Layers({ ...base, measure: 'ridesStarting', dimmed: true }).layers[1];
    expect(disc?.paint['circle-opacity']).toBe(0.35);
  });
});

describe('pairLineLayer', () => {
  it('draws one line between the two hub centres', () => {
    const declaration = pairLineLayer({ originHub: 'h1', destinationHub: 'h2' }, hubs);
    expect(declaration?.layers).toEqual([
      expect.objectContaining({
        id: 'l3-selected-pair',
        type: 'line',
        paint: expect.objectContaining({ 'line-color': '#00336e', 'line-width': 3 }) as unknown,
      }),
    ]);
    const source = declaration?.sources[L3_IDS.selectedPair];
    expect(source?.type === 'geojson' && source.data.features).toHaveLength(1);
    expect(source?.type === 'geojson' && source.data.features[0]?.geometry).toEqual({
      type: 'LineString',
      coordinates: [
        [6.1, 46.2],
        [6.2, 46.2],
      ],
    });
  });

  it('is null when a hub is unknown', () => {
    expect(pairLineLayer({ originHub: 'h1', destinationHub: 'ghost' }, hubs)).toBeNull();
    expect(pairLineLayer({ originHub: 'ghost', destinationHub: 'h1' }, hubs)).toBeNull();
  });
});
