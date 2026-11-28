import { lineWidth, linearColour } from '../../domain/home-map';
import { circlePolygon } from '../../domain/map';
import type { Showcase } from '../../domain/showcase';
import { MAP_COLOURS } from './basemap-style';
import type { GeoJsonFeature, MapDeclaration } from './map-factory';

export const HOME_IDS = {
  studyCircle: 'home-study-circle',
  hubOutlines: 'home-hub-outlines',
  pairLines: 'home-pair-lines',
} as const;

const collection = (features: readonly GeoJsonFeature[]) =>
  ({ type: 'FeatureCollection', features }) as const;

/**
 * The layers of Home's map: the study circle, the dashed hub outlines and one line per hub pair
 * with bike rides, between the hub centres. Colour (mean bike price) and width (bike rides) are
 * scaled over the drawn pairs and written into each feature.
 */
export function homeLayers(showcase: Showcase): MapDeclaration {
  const { studyCircle, hubs, hubPairs } = showcase;
  const prices = hubPairs.map((pair) => pair.meanBikePrice.value);
  const rides = hubPairs.map((pair) => pair.bikeRides.value);
  const [lowPrice, highPrice] = [Math.min(...prices), Math.max(...prices)];
  const [lowRides, highRides] = [Math.min(...rides), Math.max(...rides)];
  const lines: GeoJsonFeature[] = hubPairs.map((pair) => ({
    type: 'Feature',
    properties: {
      origin: pair.originHub,
      destination: pair.destinationHub,
      colour: linearColour(pair.meanBikePrice.value, lowPrice, highPrice),
      width: lineWidth(pair.bikeRides.value, lowRides, highRides),
    },
    geometry: {
      type: 'LineString',
      coordinates: [
        [pair.origin.lon, pair.origin.lat],
        [pair.destination.lon, pair.destination.lat],
      ],
    },
  }));
  const outlines: GeoJsonFeature[] = hubs.flatMap((hub) =>
    hub.outline === null
      ? []
      : [
          {
            type: 'Feature',
            properties: { id: hub.id },
            geometry: { type: 'Polygon', coordinates: [hub.outline.map((point) => [...point])] },
          } satisfies GeoJsonFeature,
        ],
  );
  return {
    sources: {
      [HOME_IDS.studyCircle]: {
        type: 'geojson',
        data: collection([
          {
            type: 'Feature',
            properties: {},
            geometry: {
              type: 'Polygon',
              coordinates: [circlePolygon(studyCircle.centre, studyCircle.radiusM)],
            },
          },
        ]),
      },
      [HOME_IDS.hubOutlines]: { type: 'geojson', data: collection(outlines) },
      [HOME_IDS.pairLines]: { type: 'geojson', data: collection(lines) },
    },
    layers: [
      {
        id: HOME_IDS.studyCircle,
        type: 'line',
        source: HOME_IDS.studyCircle,
        paint: { 'line-color': MAP_COLOURS.ring, 'line-width': 1.5 },
      },
      {
        id: HOME_IDS.hubOutlines,
        type: 'line',
        source: HOME_IDS.hubOutlines,
        paint: { 'line-color': MAP_COLOURS.ref, 'line-width': 1, 'line-dasharray': [3, 2] },
      },
      {
        id: HOME_IDS.pairLines,
        type: 'line',
        source: HOME_IDS.pairLines,
        layout: { 'line-cap': 'round' },
        paint: { 'line-color': ['get', 'colour'], 'line-width': ['get', 'width'] },
      },
    ],
  };
}
