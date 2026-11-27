import { ApiProblemError } from '../../application/errors';
import type { TripGateway } from '../../application/ports/trip-gateway';
import type { GeoPoint } from '../../domain/map';
import type {
  PlaceLine,
  QuotedHub,
  QuotedOption,
  QuotedPoint,
  TripQuote,
} from '../../domain/traveller';
import type { components } from './generated/schema';

type Schemas = components['schemas'];

const apiRoot = '/api/v1';

function toPoint(wire: Schemas['QuotedPointResource'] | null): QuotedPoint | null {
  if (wire === null) return null;
  return {
    status: wire.status,
    hubId: wire.hub_id,
    nearestStopName: wire.nearest_stop_name,
    nearestHubId: wire.nearest_hub_id,
    distanceFromOutlineM: wire.distance_from_outline_m?.value ?? null,
  };
}

function toHub(wire: Schemas['QuotedHubResource'] | null): QuotedHub | null {
  return wire === null ? null : { hubId: wire.hub_id, hubName: wire.hub_name };
}

const valueOrNull = (wire: Schemas['NumberResource'] | null): number | null => wire?.value ?? null;

function toOption(option: Schemas['QuotedOptionResource']): QuotedOption {
  return {
    mode: option.mode,
    mostTaken: option.most_taken,
    price: option.price.value,
    arcId: option.arc_id,
    durationS: option.duration_s.value,
    transfers: option.transfers.value,
    bikeLegs: option.bike_legs.value,
    bikePrice: valueOrNull(option.bike_price),
    ptFare: valueOrNull(option.pt_fare),
    carCost: valueOrNull(option.car_cost),
    carParkingFee: valueOrNull(option.car_parking_fee),
    flow: valueOrNull(option.flow),
    legs: option.legs.map((leg) => ({
      mode: leg.mode,
      line: leg.line,
      fromPlace: leg.from_name,
      toPlace: leg.to_name,
      durationS: leg.duration_s.value,
    })),
  };
}

function toQuote(wire: Schemas['TripQuoteResponse']): TripQuote {
  return {
    status: wire.status,
    fromPoint: toPoint(wire.from_point),
    toPoint: toPoint(wire.to_point),
    originHub: toHub(wire.origin_hub),
    destinationHub: toHub(wire.destination_hub),
    minTripDistanceM: valueOrNull(wire.min_trip_distance_m),
    noCarOption: wire.no_car_option,
    options: wire.options.map(toOption),
  };
}

function unexpected(status: number, body: unknown, path: string): ApiProblemError {
  const problem = body as Partial<Schemas['ProblemDetails']> | null;
  if (
    typeof problem === 'object' &&
    problem !== null &&
    typeof problem.code === 'string' &&
    typeof problem.title === 'string' &&
    typeof problem.detail === 'string'
  ) {
    return new ApiProblemError({
      code: problem.code,
      title: problem.title,
      detail: problem.detail,
    });
  }
  return new ApiProblemError({
    code: 'unexpected_response',
    title: `The API answered with status ${String(status)}`,
    detail: `${path} could not be read.`,
  });
}

const latLon = (point: GeoPoint) => `${String(point.lat)},${String(point.lon)}`;

export class HttpTripGateway implements TripGateway {
  private readonly fetchImpl: typeof fetch;

  constructor(fetchImpl: typeof fetch) {
    this.fetchImpl = fetchImpl;
  }

  async placeNames(instanceVersionId: string, text: string): Promise<PlaceLine[]> {
    const query = new URLSearchParams({ instance_version: instanceVersionId, q: text });
    const body = await this.read<Schemas['PlaceNameList']>(
      `${apiRoot}/place-names?${query.toString()}`,
    );
    return body.items.map((item) => ({
      name: item.name,
      kind: item.kind,
      hubId: item.hub_id,
      lat: item.lat,
      lon: item.lon,
    }));
  }

  async quote(
    pricingVersionId: string,
    period: string | null,
    from: GeoPoint | null,
    to: GeoPoint | null,
  ): Promise<TripQuote> {
    const query = new URLSearchParams({ pricing_version: pricingVersionId });
    if (period !== null) query.set('period', period);
    if (from !== null) query.set('from', latLon(from));
    if (to !== null) query.set('to', latLon(to));
    const body = await this.read<Schemas['TripQuoteResponse']>(
      `${apiRoot}/trip-quotes?${query.toString().replaceAll('%2C', ',')}`,
    );
    return toQuote(body);
  }

  private async read<T>(path: string): Promise<T> {
    let response: Response;
    try {
      response = await this.fetchImpl(path, { headers: { Accept: 'application/json' } });
    } catch (cause) {
      throw new ApiProblemError({
        code: 'api_unreachable',
        title: 'The API could not be reached',
        detail: cause instanceof Error ? cause.message : String(cause),
      });
    }
    const text = await response.text();
    let body: unknown = null;
    try {
      body = text === '' ? null : (JSON.parse(text) as unknown);
    } catch {
      body = null;
    }
    if (response.status !== 200) throw unexpected(response.status, body, path);
    return body as T;
  }
}
