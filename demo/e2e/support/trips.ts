import { expect, type APIRequestContext } from '@playwright/test';

// The stops and quotes of the traveller view, read through the API.

export interface PlaceLine {
  name: string;
  kind: string;
  hub_id: string;
  lat: number;
  lon: number;
}

interface QuotedOption {
  mode: string;
  most_taken: boolean;
  price: { value: number };
}

interface QuotedHub {
  hub_id: string;
  hub_name: string;
}

/** The first stop line of one hub, as the API lists them for a typed name. */
async function firstStopOfHub(
  request: APIRequestContext,
  instanceVersion: string,
  hub: string,
): Promise<PlaceLine> {
  const answer = await request.get('/api/v1/place-names', {
    params: { instance_version: instanceVersion, q: `Fake stop ${hub}-` },
  });
  expect(answer.status()).toBe(200);
  const stop = ((await answer.json()) as { items: PlaceLine[] }).items.find(
    (line) => line.kind === 'stop',
  );
  if (stop === undefined) throw new Error(`hub ${hub} has no stop line`);
  return stop;
}

const pointOf = (line: PlaceLine) => `${String(line.lat)},${String(line.lon)}`;

/** The API's quote of two points for a version: its status and the most taken price per mode. */
export async function quoteOf(
  request: APIRequestContext,
  pricingVersion: string,
  from: PlaceLine,
  to: PlaceLine,
): Promise<{ status: string; prices: Record<string, string> }> {
  const answer = await request.get('/api/v1/trip-quotes', {
    params: { pricing_version: pricingVersion, from: pointOf(from), to: pointOf(to) },
  });
  expect(answer.status()).toBe(200);
  const body = (await answer.json()) as { status: string; options: QuotedOption[] };
  return {
    status: body.status,
    prices: Object.fromEntries(
      body.options
        .filter((option) => option.most_taken)
        .map((option) => [option.mode, `${option.price.value.toFixed(2)} CHF`]),
    ),
  };
}

/** The first two stops of different hubs the fake city prices (some hub pairs are too close). */
export async function pricedPair(
  request: APIRequestContext,
  instanceVersion: string,
  pricingVersion: string,
): Promise<[PlaceLine, PlaceLine]> {
  const answer = await request.get(`/api/v1/instance-versions/${instanceVersion}/hubs`);
  const hubs = ((await answer.json()) as { items: { hub_id: string }[] }).items;
  const stops = await Promise.all(
    hubs.map((hub) => firstStopOfHub(request, instanceVersion, hub.hub_id)),
  );
  for (const [at, from] of stops.entries()) {
    for (const to of stops.slice(at + 1)) {
      if ((await quoteOf(request, pricingVersion, from, to)).status === 'priced') return [from, to];
    }
  }
  throw new Error('no two stops of different hubs are priced');
}

/** The hubs of a priced quote: what the heading of L-5 names. */
export async function quotedHubs(
  request: APIRequestContext,
  pricingVersion: string,
  from: PlaceLine,
  to: PlaceLine,
): Promise<{ origin: QuotedHub; destination: QuotedHub }> {
  const answer = await request.get('/api/v1/trip-quotes', {
    params: { pricing_version: pricingVersion, from: pointOf(from), to: pointOf(to) },
  });
  const body = (await answer.json()) as { origin_hub: QuotedHub; destination_hub: QuotedHub };
  return { origin: body.origin_hub, destination: body.destination_hub };
}

/** Two stop lines of one hub: the first hub with at least two stops in the fake city. */
export async function sameHubPair(
  request: APIRequestContext,
  instanceVersion: string,
): Promise<[PlaceLine, PlaceLine]> {
  const answer = await request.get(`/api/v1/instance-versions/${instanceVersion}/hubs`);
  const hubs = ((await answer.json()) as { items: { hub_id: string }[] }).items;
  for (const hub of hubs) {
    const found = await request.get('/api/v1/place-names', {
      params: { instance_version: instanceVersion, q: `Fake stop ${hub.hub_id}-` },
    });
    const stops = ((await found.json()) as { items: PlaceLine[] }).items.filter(
      (line) => line.kind === 'stop' && line.hub_id === hub.hub_id,
    );
    const [first, second] = stops;
    if (first !== undefined && second !== undefined) return [first, second];
  }
  throw new Error('no hub has two stops');
}
