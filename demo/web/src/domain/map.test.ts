import { describe, expect, it } from 'vitest';
import {
  circleBounds,
  circlePolygon,
  destinationPoint,
  distanceM,
  latestDataset,
  type CityDataset,
} from './map';

const geneva = { lat: 46.2, lon: 6.14 };

function metresBetween(a: [number, number], b: { lat: number; lon: number }): number {
  const dLat = ((a[1] - b.lat) * Math.PI) / 180;
  const dLon = ((a[0] - b.lon) * Math.PI) / 180;
  const x = dLat * 6_371_008.8;
  const y = dLon * 6_371_008.8 * Math.cos((b.lat * Math.PI) / 180);
  return Math.hypot(x, y);
}

describe('circlePolygon', () => {
  it('is a closed ring whose points lie at the radius from the centre', () => {
    const ring = circlePolygon(geneva, 3000, 32);

    expect(ring).toHaveLength(33);
    expect(ring[0]).toEqual(ring[32]);
    for (const point of ring) {
      expect(metresBetween(point, geneva)).toBeGreaterThan(2990);
      expect(metresBetween(point, geneva)).toBeLessThan(3010);
    }
  });

  it('has 65 positions by default', () => {
    expect(circlePolygon(geneva, 1000)).toHaveLength(65);
  });

  it('is empty for no step', () => {
    expect(circlePolygon(geneva, 1000, 0)).toEqual([]);
  });
});

describe('circleBounds', () => {
  it('encloses every point of the circle, tightly', () => {
    const [west, south, east, north] = circleBounds(geneva, 3000);
    const ring = circlePolygon(geneva, 3000, 360);

    for (const [lon, lat] of ring) {
      expect(lon).toBeGreaterThanOrEqual(west - 1e-6);
      expect(lon).toBeLessThanOrEqual(east + 1e-6);
      expect(lat).toBeGreaterThanOrEqual(south - 1e-6);
      expect(lat).toBeLessThanOrEqual(north + 1e-6);
    }
    expect((west + east) / 2).toBeCloseTo(geneva.lon, 9);
    expect((south + north) / 2).toBeCloseTo(geneva.lat, 9);
    expect(metresBetween([geneva.lon, north], geneva)).toBeCloseTo(3000, -1);
  });
});

describe('latestDataset', () => {
  const make = (id: string): CityDataset => ({
    id,
    centre: geneva,
    radiusM: 3000,
    availableArea: [6, 46, 6.3, 46.4],
  });

  it('is the last of the list, which comes oldest first', () => {
    expect(latestDataset([make('a'), make('b')])?.id).toBe('b');
  });

  it('is null for an empty list', () => {
    expect(latestDataset([])).toBeNull();
  });
});

describe('destinationPoint and distanceM', () => {
  it('goes east by the distance and measures it back', () => {
    const east = destinationPoint(geneva, 3000, 90);

    expect(east.lat).toBeCloseTo(geneva.lat, 3);
    expect(east.lon).toBeGreaterThan(geneva.lon);
    expect(distanceM(geneva, east)).toBeCloseTo(3000, 3);
  });

  it('goes north by the distance', () => {
    const north = destinationPoint(geneva, 1000, 0);

    expect(north.lon).toBeCloseTo(geneva.lon, 6);
    expect(distanceM(geneva, north)).toBeCloseTo(1000, 3);
  });

  it('is 0 between a point and itself', () => {
    expect(distanceM(geneva, geneva)).toBe(0);
  });

  it('agrees with the circle polygon', () => {
    const [first] = circlePolygon(geneva, 2000, 8);
    expect(first).toBeDefined();
    expect(distanceM(geneva, { lat: first?.[1] ?? 0, lon: first?.[0] ?? 0 })).toBeCloseTo(2000, 3);
  });
});
