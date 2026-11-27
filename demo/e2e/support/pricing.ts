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
    travellers: Record<string, ResultNumberAnswer>;
    displaced: ResultNumberAnswer;
    unserved: ResultNumberAnswer;
  }[];
  model_split: Record<string, ResultNumberAnswer>;
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
