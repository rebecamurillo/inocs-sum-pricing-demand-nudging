import { describe, expect, it } from 'vitest';
import type { RouteOptionLeg } from '../../domain/traveller';
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

  describe('with matched hubs and a route', () => {
    const leg = (
      mode: string,
      lineKind: RouteOptionLeg['lineKind'],
      coordinates: [number, number][] | null,
    ): RouteOptionLeg => ({
      mode,
      line: null,
      fromPlace: null,
      toPlace: null,
      durationS: 60,
      lineKind,
      coordinates,
    });
    const hubOutline = (id: string) => ({
      id,
      lat: 46.2,
      lon: 6.14,
      outline: [
        [6.1, 46.1],
        [6.2, 46.1],
        [6.2, 46.2],
        [6.1, 46.1],
      ] as [number, number][],
    });
    const full = l5Layers({
      centre: { lat: 46.2, lon: 6.14 },
      radiusM: 3000,
      stations: [],
      hubs: [hubOutline('H1'), hubOutline('H2'), hubOutline('H3')],
      matchedHubIds: ['H1', 'H3'],
      route: {
        legs: [
          leg('WALK', 'street_path', [
            [6.1, 46.1],
            [6.11, 46.11],
          ]),
          leg('BICYCLE', 'street_path', [
            [6.11, 46.11],
            [6.12, 46.12],
          ]),
          leg('TRAM', 'straight_line', [
            [6.12, 46.12],
            [6.13, 46.13],
          ]),
          leg('BUS', 'timetable_shape', [
            [6.13, 46.13],
            [6.14, 46.14],
          ]),
          leg('WALK', 'street_path', null),
        ],
      },
    });
    const layer = (id: string) => full.layers.find((l) => l.id === id);
    const lines = (id: string) => {
      const source = full.sources[id];
      if (source?.type !== 'geojson') throw new Error(`no source ${id}`);
      return source.data.features;
    };

    it('draws only the matched outlines solid, above the dashed ones', () => {
      const ids = full.layers.map((l) => l.id);
      expect(ids.indexOf(L5_IDS.matchedOutlines)).toBe(ids.indexOf(L5_IDS.hubOutlines) + 1);
      expect(layer(L5_IDS.matchedOutlines)?.paint).toEqual({
        'line-color': '#2e2d29',
        'line-width': 2,
      });
      expect(lines(L5_IDS.matchedOutlines).map((f) => f.properties.id)).toEqual(['H1', 'H3']);
    });

    it('draws one line layer per leg kind present, in its colour, width and dash', () => {
      expect(layer(L5_IDS.routeCar)).toBeUndefined();
      expect(layer(L5_IDS.routePt)?.paint).toEqual({ 'line-color': '#2a78d6', 'line-width': 3 });
      expect(layer(L5_IDS.routeBike)?.paint).toEqual({
        'line-color': '#008300',
        'line-width': 3,
        'line-dasharray': [2, 1],
      });
      expect(layer(L5_IDS.routeWalk)?.paint).toEqual({
        'line-color': '#5a6459',
        'line-width': 2,
        'line-dasharray': [1, 1.5],
      });
      expect(JSON.stringify(full)).not.toContain('#1baf7a');
    });

    it('keeps each leg as a feature with its line kind and stored coordinates', () => {
      expect(lines(L5_IDS.routePt).map((f) => f.properties)).toEqual([
        { lineKind: 'straight_line' },
        { lineKind: 'timetable_shape' },
      ]);
      expect(lines(L5_IDS.routePt)[0]?.geometry).toEqual({
        type: 'LineString',
        coordinates: [
          [6.12, 46.12],
          [6.13, 46.13],
        ],
      });
      expect(lines(L5_IDS.routeWalk)).toHaveLength(1);
    });

    it('puts the route above the bike stations and adds nothing without one', () => {
      const ids = full.layers.map((l) => l.id);
      expect(ids.indexOf(L5_IDS.routeWalk)).toBeGreaterThan(ids.indexOf(L5_IDS.bikeStations));
      expect(declaration.layers).toHaveLength(3);
    });

    it('draws a car route in the car colour', () => {
      const car = l5Layers({
        centre: { lat: 46.2, lon: 6.14 },
        radiusM: 1,
        stations: [],
        hubs: [],
        route: {
          legs: [
            leg('CAR', 'street_path', [
              [6.1, 46.1],
              [6.2, 46.2],
            ]),
          ],
        },
      });
      expect(car.layers.find((l) => l.id === L5_IDS.routeCar)?.paint).toEqual({
        'line-color': '#eb6834',
        'line-width': 3,
      });
    });
  });
});
