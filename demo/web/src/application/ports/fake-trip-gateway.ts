import type { GeoPoint } from '../../domain/map';
import type {
  PlaceLine,
  QuotedHub,
  QuotedPoint,
  QuotedOption,
  TripQuote,
} from '../../domain/traveller';
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

const leg = (
  mode: string,
  line: string | null,
  fromPlace: string | null,
  toPlace: string | null,
  durationS: number,
) => ({ mode, line, fromPlace, toPlace, durationS });

const optionBase: QuotedOption = {
  mode: 'car',
  mostTaken: true,
  price: 0,
  arcId: 'arc',
  durationS: 600,
  transfers: 0,
  bikeLegs: 0,
  bikePrice: null,
  ptFare: null,
  carCost: null,
  carParkingFee: null,
  flow: null,
  legs: [],
};

/** A price per mode that depends on the version's letter, so a switch changes it. */
export function sampleOptions(pricingVersionId: string): QuotedOption[] {
  const base = (pricingVersionId.codePointAt(pricingVersionId.length - 1) ?? 65) - 64;
  const bikePrice = base * 0.5;
  return [
    {
      ...optionBase,
      mode: 'pt_bike',
      mostTaken: false,
      price: 9.99,
      arcId: 'b2',
      durationS: 1500,
      transfers: 1,
      bikeLegs: 2,
      bikePrice: 3.99,
      ptFare: 2,
      flow: 3,
      legs: [
        leg('WALK', null, 'A', 'Plainpalais', 60),
        leg('BICYCLE', null, 'Plainpalais', 'Bel-Air', 400),
        leg('TRAM', '12', 'Bel-Air', 'Rive', 600),
        leg('BICYCLE', null, 'Rive', 'Cornavin', 400),
      ],
    },
    {
      ...optionBase,
      mode: 'pt_bike',
      mostTaken: false,
      price: 4.2,
      arcId: 'b3',
      durationS: 1320,
      transfers: 0,
      bikeLegs: 1,
      bikePrice: 2.2,
      ptFare: 2,
      flow: 1,
      legs: [
        leg('TRAM', '15', 'Plainpalais', 'Rive', 900),
        leg('BICYCLE', null, 'Rive', 'Cornavin', 420),
      ],
    },
    {
      ...optionBase,
      mode: 'pt_bike',
      price: 2 + bikePrice,
      arcId: 'b1',
      durationS: 1080,
      transfers: 1,
      bikeLegs: 1,
      bikePrice,
      ptFare: 2,
      flow: 8,
      legs: [
        leg('WALK', null, 'A', 'Plainpalais', 120),
        leg('TRAM', '12', 'Plainpalais', 'Rive', 700),
        leg('BICYCLE', null, 'Rive', 'Cornavin', 260),
      ],
    },
    {
      ...optionBase,
      mode: 'pt_only',
      price: 2,
      arcId: 'p1',
      durationS: 1500,
      transfers: 2,
      ptFare: 2,
      flow: 5,
      legs: [leg('TRAM', '12', 'Plainpalais', 'Cornavin', 1500)],
    },
    {
      ...optionBase,
      mode: 'car',
      price: 4.5,
      arcId: 'c1',
      durationS: 540,
      carCost: 1.7,
      carParkingFee: 2.8,
      flow: 4,
      legs: [leg('CAR', null, 'Plainpalais', 'Cornavin', 540)],
    },
  ];
}

export interface FakeTrips {
  readonly gateway: TripGateway;
  /** Replaces fields of every following quote (a status, an option list); null restores them. */
  readonly answer: (patch: Partial<TripQuote> | null) => void;
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
  let patch: Partial<TripQuote> | null = null;
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
      const same = matched && fromPoint.hubId === toPoint.hubId;
      const hub = (point: QuotedPoint | null): QuotedHub | null =>
        matched && point?.hubId != null
          ? { hubId: point.hubId, hubName: point.nearestStopName ?? '' }
          : null;
      const quote: TripQuote = {
        status: same ? 'same_hub' : matched ? 'priced' : 'one_point',
        fromPoint,
        toPoint,
        originHub: hub(fromPoint),
        destinationHub: hub(toPoint),
        minTripDistanceM: null,
        noCarOption: matched && !same ? false : null,
        options: matched && !same ? sampleOptions(pricingVersionId) : [],
        ...patch,
      };
      return Promise.resolve(quote);
    },
  };
  return {
    gateway,
    placeCalls,
    quoteCalls,
    answer: (next) => {
      patch = next;
    },
  };
}

export const emptyTrips: TripGateway = fakeTrips().gateway;
