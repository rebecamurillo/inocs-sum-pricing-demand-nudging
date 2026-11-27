/** Geometry for the map: pure functions on degrees and metres. */

export interface GeoPoint {
  readonly lat: number;
  readonly lon: number;
}

/** [west, south, east, north] in degrees. */
export type GeoBounds = readonly [number, number, number, number];

/** A city data set as the map needs it: where its preset study circle is. */
export interface CityDataset {
  readonly id: string;
  readonly centre: GeoPoint;
  readonly radiusM: number;
  readonly availableArea: GeoBounds;
}

const EARTH_RADIUS_M = 6_371_008.8;
const DEG = Math.PI / 180;

/** The ring of [lon, lat] positions of a circle on the sphere, closed (first = last). */
export function circlePolygon(centre: GeoPoint, radiusM: number, steps = 64): [number, number][] {
  const angular = radiusM / EARTH_RADIUS_M;
  const lat1 = centre.lat * DEG;
  const lon1 = centre.lon * DEG;
  const ring: [number, number][] = [];
  for (let step = 0; step < steps; step += 1) {
    const bearing = (2 * Math.PI * step) / steps;
    const lat2 = Math.asin(
      Math.sin(lat1) * Math.cos(angular) + Math.cos(lat1) * Math.sin(angular) * Math.cos(bearing),
    );
    const lon2 =
      lon1 +
      Math.atan2(
        Math.sin(bearing) * Math.sin(angular) * Math.cos(lat1),
        Math.cos(angular) - Math.sin(lat1) * Math.sin(lat2),
      );
    ring.push([lon2 / DEG, lat2 / DEG]);
  }
  const first = ring[0];
  if (first !== undefined) ring.push(first);
  return ring;
}

/** The bounding box of the circle: it reaches `radiusM` north, south, east and west. */
export function circleBounds(centre: GeoPoint, radiusM: number): GeoBounds {
  const dLat = radiusM / EARTH_RADIUS_M / DEG;
  const dLon = dLat / Math.cos(centre.lat * DEG);
  return [centre.lon - dLon, centre.lat - dLat, centre.lon + dLon, centre.lat + dLat];
}

/** The API lists data sets oldest first: the most recent is the last one. */
export function latestDataset(datasets: readonly CityDataset[]): CityDataset | null {
  return datasets.at(-1) ?? null;
}

/** What the L-1 layers draw: a public transport stop (`pt`) or a bike station (`bs`). */
export interface MapStation {
  readonly id: string;
  readonly kind: 'pt' | 'bs';
  readonly lat: number;
  readonly lon: number;
}

export interface MapHub {
  readonly id: string;
  readonly lat: number;
  readonly lon: number;
  /** One closed ring of [lon, lat] positions, or null. */
  readonly outline: readonly (readonly [number, number])[] | null;
}

export interface MapHubPair {
  readonly originHub: string;
  readonly destinationHub: string;
}
