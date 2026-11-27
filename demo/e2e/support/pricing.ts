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
