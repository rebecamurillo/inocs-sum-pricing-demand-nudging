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

/** The point `distanceM` metres from `from` along `bearingDeg` (0 north, 90 east) on the sphere. */
export function destinationPoint(from: GeoPoint, distanceM: number, bearingDeg: number): GeoPoint {
  const angular = distanceM / EARTH_RADIUS_M;
  const bearing = bearingDeg * DEG;
  const lat1 = from.lat * DEG;
  const lat2 = Math.asin(
    Math.sin(lat1) * Math.cos(angular) + Math.cos(lat1) * Math.sin(angular) * Math.cos(bearing),
  );
  const lon2 =
    from.lon * DEG +
    Math.atan2(
      Math.sin(bearing) * Math.sin(angular) * Math.cos(lat1),
      Math.cos(angular) - Math.sin(lat1) * Math.sin(lat2),
    );
  return { lat: lat2 / DEG, lon: lon2 / DEG };
}

/** The great-circle distance between two points, in metres (haversine). */
export function distanceM(a: GeoPoint, b: GeoPoint): number {
  const dLat = (b.lat - a.lat) * DEG;
  const dLon = (b.lon - a.lon) * DEG;
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(a.lat * DEG) * Math.cos(b.lat * DEG) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.min(1, Math.sqrt(h)));
}
