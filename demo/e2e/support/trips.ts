import { expect, type APIRequestContext } from '@playwright/test';

// The stops and quotes of the traveller view, read through the API.

export interface PlaceLine {
  name: string;
  kind: string;
  hub_id: string;
  lat: number;
  lon: number;
}

interface QuotedLeg {
  mode: string;
  line: string | null;
  from_name: string | null;
  to_name: string | null;
  duration_s: { value: number };
}

interface QuotedOption {
  mode: string;
  most_taken: boolean;
  price: { value: number };
  legs: QuotedLeg[];
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

/** The first ordered pair of stops of different hubs whose quote offers several PT + bike options. */
export async function pairWithOtherBikeOptions(
  request: APIRequestContext,
  instanceVersion: string,
  pricingVersion: string,
): Promise<[PlaceLine, PlaceLine]> {
  const answer = await request.get(`/api/v1/instance-versions/${instanceVersion}/hubs`);
  const hubs = ((await answer.json()) as { items: { hub_id: string }[] }).items;
  const stops = await Promise.all(
    hubs.map((hub) => firstStopOfHub(request, instanceVersion, hub.hub_id)),
  );
  for (const from of stops) {
    for (const to of stops) {
      if (from.hub_id === to.hub_id) continue;
      const quoted = await request.get('/api/v1/trip-quotes', {
        params: { pricing_version: pricingVersion, from: pointOf(from), to: pointOf(to) },
      });
      const body = (await quoted.json()) as { status: string; options: QuotedOption[] };
      if (body.status === 'priced' && body.options.filter((o) => o.mode === 'pt_bike').length > 1) {
        return [from, to];
      }
    }
  }
  throw new Error('no pair of stops has several PT + bike options');
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

const TRANSIT_LABELS: Record<string, string> = { TRAM: 'Tram', BUS: 'Bus', RAIL: 'Train' };

/** The leg line L-5 lists for a leg, written from the API's fields (UX: "Tram 12 · A → B · 5 min"). */
function legLine(leg: QuotedLeg): string {
  const minutes = `${String(Math.round(leg.duration_s.value / 60))} min`;
  if (leg.mode === 'WALK' || leg.mode === 'FOOT') return `Walk · ${minutes}`;
  if (leg.mode === 'CAR') return `Car · ${minutes}`;
  const span =
    leg.from_name !== null && leg.to_name !== null ? `${leg.from_name} → ${leg.to_name}` : null;
  let head = 'Shared bike';
  if (leg.mode !== 'BICYCLE') {
    const lower = leg.mode.toLowerCase();
    const label = TRANSIT_LABELS[leg.mode] ?? `${lower.charAt(0).toUpperCase()}${lower.slice(1)}`;
    head = leg.line === null ? label : `${label} ${leg.line}`;
  }
  return [head, span, minutes].filter((part) => part !== null).join(' · ');
}

/** The leg lines of the most taken option of a mode in the API's quote of two points. */
export async function legLinesOf(
  request: APIRequestContext,
  pricingVersion: string,
  from: PlaceLine,
  to: PlaceLine,
  mode: string,
): Promise<string[]> {
  const answer = await request.get('/api/v1/trip-quotes', {
    params: { pricing_version: pricingVersion, from: pointOf(from), to: pointOf(to) },
  });
  expect(answer.status()).toBe(200);
  const body = (await answer.json()) as { options: QuotedOption[] };
  const option = body.options.find((item) => item.mode === mode && item.most_taken);
  if (option === undefined) throw new Error(`the quote has no ${mode} option`);
  return option.legs.map(legLine);
}
