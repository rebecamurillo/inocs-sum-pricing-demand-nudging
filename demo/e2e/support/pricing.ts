import { expect, type APIRequestContext } from '@playwright/test';

export interface CreatedPricingVersion {
  /** The pricing version's id, `geneva-3km.v1.A`. */
  id: string;
  letter: string;
}

/** Starts a pricing version (a draft) on a built instance version through the API. */
export async function createPricingVersion(
  request: APIRequestContext,
  instanceVersionId: string,
  body: { name?: string; based_on?: string } = {},
): Promise<CreatedPricingVersion> {
  const created = await request.post(
    `/api/v1/instance-versions/${instanceVersionId}/pricing-versions`,
    {
      data: body,
    },
  );
  expect(created.status()).toBe(201);
  return (await created.json()) as CreatedPricingVersion;
}

/** Asks for the run of a pricing version (the same request seals a draft and runs a failed one again). */
export async function runPricingVersion(request: APIRequestContext, id: string) {
  return request.post(`/api/v1/pricing-versions/${id}/runs`);
}

export interface RunStepAnswer {
  step: string;
  state: string;
  reason: string | null;
}

export interface PricingRunAnswer {
  id: string;
  kind: string;
  state: string;
  subject: { type: string; id: string };
  steps: RunStepAnswer[];
  failure: { step: string | null; code: string; reason: string } | null;
}

const RUN_TIMEOUT_MS = 60_000;

/** Waits until the run is in the state and returns it as the API gives it. */
export async function waitForRun(
  request: APIRequestContext,
  runId: string,
  state: string,
): Promise<PricingRunAnswer> {
  let found: PricingRunAnswer | undefined;
  await expect
    .poll(
      async () => {
        found = (await (await request.get(`/api/v1/runs/${runId}`)).json()) as PricingRunAnswer;
        return found.state;
      },
      { timeout: RUN_TIMEOUT_MS, message: `run ${runId} is ${state}` },
    )
    .toBe(state);
  if (found === undefined) throw new Error(`run ${runId} was not read`);
  return found;
}

/** Asks for the version's stored solve to be simulated again with the worker's current rule. */
export async function simulatePricingVersion(request: APIRequestContext, id: string) {
  return request.post(`/api/v1/pricing-versions/${id}/simulations`);
}

/** Waits until `/system-status` reports the rule version the live worker recorded on its heartbeat. */
export async function waitForSimulationRule(
  request: APIRequestContext,
  version: number,
): Promise<void> {
  await expect
    .poll(
      async () => {
        const status = (await (await request.get('/api/v1/system-status')).json()) as {
          simulation_rule: { version: number } | null;
        };
        return status.simulation_rule?.version ?? null;
      },
      {
        timeout: RUN_TIMEOUT_MS,
        message: `the worker records simulation rule version ${String(version)}`,
      },
    )
    .toBe(version);
}

/** Marks a finished version and period as the home page's result (`PUT /showcase`). */
export async function putShowcase(
  request: APIRequestContext,
  pricingVersionId: string,
  periodId: string,
): Promise<void> {
  const marked = await request.put('/api/v1/showcase', {
    data: { pricing_version_id: pricingVersionId, period_id: periodId },
  });
  expect(marked.status()).toBe(200);
}

/** The numbers and texts of `GET /showcase` that Home writes on its tile. */
export interface ShowcaseAnswer {
  letter: string;
  instance_version_name: string;
  scope: { city: string; radius_km: { value: number }; period_label: string };
  car_share_difference: { value: number; unit: string; source: string; group: string };
  flat_price: { value: number };
  rule: { id: string; version: number; rule_current: boolean };
  hubs: { id: string }[];
  hub_pairs: { bike_rides: { value: number } }[];
}

/** Reads the showcase Home draws. */
export async function readShowcase(request: APIRequestContext): Promise<ShowcaseAnswer> {
  const answer = await request.get('/api/v1/showcase');
  expect(answer.status()).toBe(200);
  return (await answer.json()) as ShowcaseAnswer;
}

/** One number of the result route: `{value, unit, source, group}`. */
export interface ResultNumberAnswer {
  value: number;
  unit: string;
  source: string;
}

export interface PricingResultAnswer {
  pricing_version_id: string;
  period_id: string;
  goals: {
    name: string;
    model: ResultNumberAnswer | null;
    model_prices: ResultNumberAnswer | null;
    flat: ResultNumberAnswer | null;
    change: ResultNumberAnswer | null;
  }[];
  simulations: {
    price_scheme: 'model_prices' | 'flat';
    rule_id: string;
    rule_version: number;
    rule_parameters: Record<string, number>;
    bike_rides: ResultNumberAnswer;
    revenue: ResultNumberAnswer;
    cost: ResultNumberAnswer;
    travellers: Record<string, ResultNumberAnswer>;
    displaced: ResultNumberAnswer;
    unserved: ResultNumberAnswer;
  }[];
  model_split: Record<string, ResultNumberAnswer>;
  advanced: { solver_status_name: string; numbers: Record<string, ResultNumberAnswer> };
  provenance: {
    package_version: string | null;
    package_commit: string | null;
    gurobi_version: string;
    licence_kind: string;
    demonstrator_version: string;
    timetable_operator: string | null;
    bike_stations_source_url: string | null;
  };
}

/** Runs a draft of a built instance version to its result and returns the result as the API gives it. */
export async function runToResult(
  request: APIRequestContext,
  id: string,
): Promise<PricingResultAnswer> {
  const queued = await runPricingVersion(request, id);
  expect(queued.status()).toBe(202);
  const run = (await queued.json()) as { id: string };
  await waitForRun(request, run.id, 'succeeded');
  const answer = await request.get(`/api/v1/pricing-versions/${id}/result`);
  expect(answer.status()).toBe(200);
  return (await answer.json()) as PricingResultAnswer;
}

/** Starts a version with these goals and runs it to its result; returns its id and letter. */
export async function finishVersion(
  request: APIRequestContext,
  instanceVersionId: string,
  name: string,
  goals: Record<string, number> = {},
): Promise<CreatedPricingVersion> {
  const created = await createPricingVersion(request, instanceVersionId, { name });
  if (Object.keys(goals).length > 0) {
    const changed = await request.patch(`/api/v1/pricing-versions/${created.id}`, { data: goals });
    expect(changed.status()).toBe(200);
  }
  await runToResult(request, created.id);
  return created;
}

/** The simulation of a scheme and its travellers per mode, `[car, pt_only, pt_bike]`. */
export function simulationOf(result: PricingResultAnswer, scheme: 'model_prices' | 'flat') {
  const found = result.simulations.find((item) => item.price_scheme === scheme);
  const empty = { value: Number.NaN, unit: '', source: '' };
  const count = (mode: string) => found?.travellers[mode]?.value ?? Number.NaN;
  return {
    car: count('car'),
    ptOnly: count('pt_only'),
    ptBike: count('pt_bike'),
    displaced: (found?.displaced ?? empty).value,
    unserved: (found?.unserved ?? empty).value,
  };
}

/** The insight title L-3 writes for the points of fewer (or more) simulated car travellers. */
export function insightTitle(letter: string, points: number): string {
  const head = `With Version ${letter}'s prices, `;
  const fewer = `${String(points)} in 100 fewer simulated travellers take the car than with the flat price`;
  const more = `${String(-points)} in 100 more simulated travellers take the car than with the flat price`;
  const same = 'as many simulated travellers take the car as with the flat price';
  return head + (points > 0 ? fewer : points < 0 ? more : same);
}

interface NumberAnswer {
  value: number;
}

export interface LegAnswer {
  mode: string;
  line: string | null;
  from_place: string | null;
  to_place: string | null;
}

export interface HubPairResultAnswer {
  origin_hub: string;
  destination_hub: string;
  mean_bike_price: NumberAnswer | null;
  min_bike_price: NumberAnswer | null;
  max_bike_price: NumberAnswer | null;
  travellers: Record<string, NumberAnswer>;
  options: {
    arc_id: string;
    mode: string;
    legs: LegAnswer[];
    duration: NumberAnswer;
    bike_price: NumberAnswer | null;
    riders: NumberAnswer | null;
  }[];
}

export interface HubResultAnswer {
  hub_id: string;
  label: string;
}

/** The model's price and flow per hub pair, as `GET …/hub-pair-results` answers. */
export async function hubPairResultsOf(
  request: APIRequestContext,
  id: string,
): Promise<HubPairResultAnswer[]> {
  const answer = await request.get(`/api/v1/pricing-versions/${id}/hub-pair-results`);
  expect(answer.status()).toBe(200);
  return ((await answer.json()) as { items: HubPairResultAnswer[] }).items;
}

/** The model's results per hub, as `GET …/hub-results` answers. */
export async function hubResultsOf(
  request: APIRequestContext,
  id: string,
): Promise<HubResultAnswer[]> {
  const answer = await request.get(`/api/v1/pricing-versions/${id}/hub-results`);
  expect(answer.status()).toBe(200);
  return ((await answer.json()) as { items: HubResultAnswer[] }).items;
}

/** The pair's offered PT + bike options, cheapest first: what the open row lists. */
export function offeredOptionsOf(pair: HubPairResultAnswer) {
  return pair.options
    .filter((option) => option.mode === 'pt_bike' && option.bike_price !== null)
    .sort((a, b) => (a.bike_price?.value ?? 0) - (b.bike_price?.value ?? 0));
}

const TRANSIT: Record<string, string> = {
  TRAM: 'Tram',
  BUS: 'Bus',
  RAIL: 'Train',
  SUBWAY: 'Metro',
  FERRY: 'Boat',
};

/** An option named by its legs, walking left out: "Tram 12 → Rive · bike Rive → Eaux-Vives". */
export function optionNameOf(legs: LegAnswer[]): string {
  return legs
    .filter((leg) => leg.mode !== 'FOOT' && leg.mode !== 'WALK')
    .map((leg) => {
      if (leg.mode === 'BICYCLE') {
        return leg.from_place === null || leg.to_place === null
          ? 'bike'
          : `bike ${leg.from_place} → ${leg.to_place}`;
      }
      const lower = leg.mode.toLowerCase();
      const label = TRANSIT[leg.mode] ?? `${lower.charAt(0).toUpperCase()}${lower.slice(1)}`;
      const named = leg.line === null ? label : `${label} ${leg.line}`;
      return leg.to_place === null ? named : `${named} → ${leg.to_place}`;
    })
    .join(' · ');
}

/** The value, or a failure naming what is missing (a scenario's way to narrow without branching). */
export function must<T>(value: T | undefined, what: string): T {
  if (value === undefined) throw new Error(`${what} is missing`);
  return value;
}

/** What the "Mean bike price" cell of a pair's row says: the mean, or the sentence of its state. */
export function priceCellOf(pair: HubPairResultAnswer): string {
  if (pair.mean_bike_price !== null) return pair.mean_bike_price.value.toFixed(2);
  return pair.min_bike_price === null ? 'no bike option offered' : '— no bike rides';
}

/** A pair's travellers per mode. */
export function travellersOf(pair: HubPairResultAnswer) {
  const count = (mode: string) => pair.travellers[mode]?.value ?? Number.NaN;
  return { car: count('car'), pt: count('pt_only'), ptBike: count('pt_bike') };
}
