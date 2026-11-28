import { describe, expect, it } from 'vitest';
import { sampleShowcase } from '../../application/ports/fake-pricing-gateway';
import { HOME_RAMP } from '../../domain/home-map';
import { homeLayers, HOME_IDS } from './home-layers';
import type { GeoJsonCollection } from './map-factory';

const data = (id: string): GeoJsonCollection => {
  const source = homeLayers(sampleShowcase).sources[id];
  if (source?.type !== 'geojson') throw new Error(`no data source ${id}`);
  return source.data;
};

describe('homeLayers', () => {
  it('declares the circle, the dashed hub outlines and the pair lines, in that order', () => {
    const { layers } = homeLayers(sampleShowcase);

    expect(layers.map((layer) => layer.id)).toEqual([
      HOME_IDS.studyCircle,
      HOME_IDS.hubOutlines,
      HOME_IDS.pairLines,
    ]);
    expect(layers[0]?.paint['line-color']).toBe('#b7bcb5');
    expect(layers[1]?.paint['line-color']).toBe('#949c93');
    expect(layers[1]?.paint['line-dasharray']).toEqual([3, 2]);
  });

  it('draws one outline per hub that has one', () => {
    expect(data(HOME_IDS.hubOutlines).features).toHaveLength(1);
  });

  it('draws one line per pair between its hub centres, on the scales of the drawn pairs', () => {
    const { features } = data(HOME_IDS.pairLines);

    expect(features).toHaveLength(2);
    expect(features[0]?.geometry).toEqual({
      type: 'LineString',
      coordinates: [
        [6.13, 46.2],
        [6.15, 46.21],
      ],
    });
    // The first pair has the lowest price (0.75) and the most rides (8).
    expect(features[0]?.properties).toMatchObject({ colour: HOME_RAMP.low, width: 7 });
    expect(features[1]?.properties).toMatchObject({ colour: HOME_RAMP.high, width: 1 });
  });

  it('draws every line at the midpoint when all pairs share one value', () => {
    const [first] = sampleShowcase.hubPairs;
    if (first === undefined) throw new Error('fixture');
    const declaration = homeLayers({ ...sampleShowcase, hubPairs: [first, { ...first }] });
    const source = declaration.sources[HOME_IDS.pairLines];
    if (source?.type !== 'geojson') throw new Error('source');

    for (const feature of source.data.features) {
      expect(feature.properties).toMatchObject({ colour: '#728fb2', width: 4 });
    }
  });
});
