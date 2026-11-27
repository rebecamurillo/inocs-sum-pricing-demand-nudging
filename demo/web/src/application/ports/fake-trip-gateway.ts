import type { GeoPoint } from '../../domain/map';
import type { PlaceLine, QuotedPoint, QuotedOption, TripQuote } from '../../domain/traveller';
import type { TripGateway } from './trip-gateway';

export const samplePlaces: readonly PlaceLine[] = [
  { name: 'Plainpalais', kind: 'stop', hubId: 'H4', lat: 46.199, lon: 6.14 },
  { name: 'Plainpalais', kind: 'bike_station', hubId: 'H4', lat: 46.1991, lon: 6.1402 },
  { name: 'Cornavin', kind: 'stop', hubId: 'H1', lat: 46.2102, lon: 6.1424 },
];

const HUB_RADIUS_DEG = 0.004;

/** The sample hub nearest to a point: H4 near Plainpalais, H1 near Cornavin, else no hub. */
export function sampleQuotedPoint(point: GeoPoint): QuotedPoint {
  const near = (place: PlaceLine) =>
    Math.abs(place.lat - point.lat) < HUB_RADIUS_DEG &&
    Math.abs(place.lon - point.lon) < HUB_RADIUS_DEG;
  const place = samplePlaces.find((candidate) => candidate.kind === 'stop' && near(candidate));
  if (place === undefined) {
    return {
      status: 'no_hub_here',
      hubId: null,
      nearestStopName: null,
      nearestHubId: 'H7',
      distanceFromOutlineM: 412.6,
    };
  }
  return {
    status: 'matched',
    hubId: place.hubId,
    nearestStopName: place.name,
    nearestHubId: null,
    distanceFromOutlineM: null,
  };
}

/** A price per mode that depends on the version's letter, so a switch changes it. */
export function sampleOptions(pricingVersionId: string): QuotedOption[] {
  const base = (pricingVersionId.codePointAt(pricingVersionId.length - 1) ?? 65) - 64;
  return [
    { mode: 'pt_bike', mostTaken: false, price: 9.99 },
    { mode: 'pt_bike', mostTaken: true, price: 2 + base * 0.5 },
    { mode: 'pt_only', mostTaken: true, price: 2 },
    { mode: 'car', mostTaken: true, price: 4.5 },
  ];
}

export interface FakeTrips {
  readonly gateway: TripGateway;
  readonly placeCalls: { instanceVersionId: string; text: string }[];
  readonly quoteCalls: {
    pricingVersionId: string;
    period: string | null;
    from: GeoPoint | null;
    to: GeoPoint | null;
  }[];
}

/** In-memory trips: the sample places and hubs; every call is recorded. */
export function fakeTrips(places: readonly PlaceLine[] = samplePlaces): FakeTrips {
  const placeCalls: FakeTrips['placeCalls'] = [];
  const quoteCalls: FakeTrips['quoteCalls'] = [];
  const gateway: TripGateway = {
    placeNames: (instanceVersionId, text) => {
      placeCalls.push({ instanceVersionId, text });
      const wanted = text.toLowerCase();
      return Promise.resolve(
        text.length < 2 ? [] : places.filter((place) => place.name.toLowerCase().includes(wanted)),
      );
    },
    quote: (pricingVersionId, period, from, to) => {
      quoteCalls.push({ pricingVersionId, period, from, to });
      const fromPoint = from === null ? null : sampleQuotedPoint(from);
      const toPoint = to === null ? null : sampleQuotedPoint(to);
      const matched = fromPoint?.status === 'matched' && toPoint?.status === 'matched';
      const quote: TripQuote = {
        status: matched ? 'priced' : 'one_point',
        fromPoint,
        toPoint,
        options: matched ? sampleOptions(pricingVersionId) : [],
      };
      return Promise.resolve(quote);
    },
  };
  return { gateway, placeCalls, quoteCalls };
}

export const emptyTrips: TripGateway = fakeTrips().gateway;
