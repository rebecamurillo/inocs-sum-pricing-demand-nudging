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
