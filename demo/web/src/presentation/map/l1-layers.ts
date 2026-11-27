import {
  circlePolygon,
  type GeoPoint,
  type MapHub,
  type MapHubPair,
  type MapStation,
} from '../../domain/map';
import { MAP_COLOURS } from './basemap-style';
import type { GeoJsonFeature, MapDeclaration } from './map-factory';

interface L1Input {
  readonly centre: GeoPoint;
  readonly radiusM: number;
  readonly stations: readonly MapStation[];
  readonly hubs: readonly MapHub[];
  readonly hubPairs: readonly MapHubPair[];
}

export const L1_IDS = {
  studyCircle: 'l1-study-circle',
  stops: 'l1-stops',
  bikeStations: 'l1-bike-stations',
  hubOutlines: 'l1-hub-outlines',
  hubPairs: 'l1-hub-pairs',
} as const;

const collection = (features: readonly GeoJsonFeature[]) =>
  ({ type: 'FeatureCollection', features }) as const;

const point = (station: MapStation): GeoJsonFeature => ({
  type: 'Feature',
  properties: { id: station.id },
  geometry: { type: 'Point', coordinates: [station.lon, station.lat] },
});

/**
 * The layers of the instance view L-1: the study circle, the stops, the bike stations, the
 * hub outlines and, in one line layer, a line between the two hubs' centres per hub pair.
 * A pair that names a hub the instance does not have is left out.
 */
export function l1Layers({ centre, radiusM, stations, hubs, hubPairs }: L1Input): MapDeclaration {
  const centreOf = new Map(hubs.map((hub) => [hub.id, [hub.lon, hub.lat] as const]));
  const pairLines: GeoJsonFeature[] = [];
  for (const pair of hubPairs) {
    const from = centreOf.get(pair.originHub);
    const to = centreOf.get(pair.destinationHub);
    if (from === undefined || to === undefined) continue;
    pairLines.push({
      type: 'Feature',
      properties: { origin: pair.originHub, destination: pair.destinationHub },
      geometry: { type: 'LineString', coordinates: [from, to] },
    });
  }
  const outlines: GeoJsonFeature[] = hubs.flatMap((hub) =>
    hub.outline === null
      ? []
      : [
          {
            type: 'Feature',
            properties: { id: hub.id },
            geometry: { type: 'Polygon', coordinates: [hub.outline] },
          } satisfies GeoJsonFeature,
        ],
  );

  return {
    sources: {
      [L1_IDS.studyCircle]: {
        type: 'geojson',
        data: collection([
          {
            type: 'Feature',
            properties: {},
            geometry: { type: 'Polygon', coordinates: [circlePolygon(centre, radiusM)] },
          },
        ]),
      },
      [L1_IDS.hubPairs]: { type: 'geojson', data: collection(pairLines) },
      [L1_IDS.hubOutlines]: { type: 'geojson', data: collection(outlines) },
      [L1_IDS.stops]: {
        type: 'geojson',
        data: collection(stations.filter((s) => s.kind === 'pt').map(point)),
      },
      [L1_IDS.bikeStations]: {
        type: 'geojson',
        data: collection(stations.filter((s) => s.kind === 'bs').map(point)),
      },
    },
    // Drawn bottom to top.
    layers: [
      {
        id: L1_IDS.studyCircle,
        type: 'fill',
        source: L1_IDS.studyCircle,
        paint: {
          'fill-color': MAP_COLOURS.ring,
          'fill-opacity': 0.18,
          'fill-outline-color': MAP_COLOURS.ring,
        },
      },
      {
        id: L1_IDS.hubPairs,
        type: 'line',
        source: L1_IDS.hubPairs,
        paint: { 'line-color': MAP_COLOURS.ref, 'line-width': 0.5, 'line-opacity': 0.5 },
      },
      {
        id: L1_IDS.hubOutlines,
        type: 'line',
        source: L1_IDS.hubOutlines,
        paint: { 'line-color': MAP_COLOURS.ref, 'line-width': 1.5, 'line-dasharray': [2, 2] },
      },
      {
        id: L1_IDS.stops,
        type: 'circle',
        source: L1_IDS.stops,
        paint: { 'circle-color': MAP_COLOURS.stop, 'circle-radius': 3 },
      },
      {
        id: L1_IDS.bikeStations,
        type: 'circle',
        source: L1_IDS.bikeStations,
        paint: {
          'circle-color': MAP_COLOURS.bike,
          'circle-radius': 4,
          'circle-stroke-color': MAP_COLOURS.bikeRing,
          'circle-stroke-width': 1.5,
        },
      },
    ],
  };
}
