import { describe, expect, it } from 'vitest';
import {
  fakePricing,
  pricingRulesOf,
  samplePricingDraft,
  samplePricingGoals,
  samplePricingResult,
  sampleHubPairResults,
  sampleHubResults,
  sampleSealedPricing,
  sampleStoredSimulations,
} from './fake-pricing-gateway';

describe('the in-memory pricing gateway', () => {
  it('reports every amount and the options as rules', () => {
    const rules = pricingRulesOf({
      ...samplePricingGoals,
      lowest_price_chf: -0.5,
      max_displayed_options: 0,
    });
    expect(rules.filter((rule) => !rule.passed).map((rule) => [rule.field, rule.message])).toEqual([
      ['lowest_price_chf', 'Lowest price of a ride must be 0 or more: now -0.5'],
      ['max_displayed_options', 'Options shown per hub pair must be at least 1: now 0'],
    ]);
  });

  it('starts drafts under running letters, keeping the values of the last sealed version', async () => {
    const { gateway } = fakePricing();

    const first = await gateway.create('geneva-3km.v1');
    expect(first.keptFrom).toBeNull();
    await gateway.run(first.id);
    const second = await gateway.create('geneva-3km.v1');

    expect([first.letter, second.letter]).toEqual(['A', 'B']);
    expect(second.keptFrom).toEqual({ id: 'geneva-3km.v1.A', letter: 'A' });
  });

  it('starts a duplicate from the goals of the version it names and keeps the run id of a run', async () => {
    const { gateway, versions } = fakePricing([
      samplePricingDraft({ id: 'geneva-3km.v1.A', letter: 'A', goals: { pt_fare_chf: 3 } }),
    ]);

    const copy = await gateway.create('geneva-3km.v1', 'geneva-3km.v1.A');
    await gateway.run(copy.id);

    expect(copy.basedOnId).toBe('geneva-3km.v1.A');
    expect(copy.goals.pt_fare_chf).toBe(3);
    expect(versions().find((version) => version.id === copy.id)?.runId).toBe('run-pricing-B');
  });

  it('keeps a patched value and name as sent and answers the rules', async () => {
    const { gateway } = fakePricing([samplePricingDraft()]);

    const answer = await gateway.patch('geneva-3km.v1.D', { cost_bike_chf: -1, name: ' Cheaper ' });

    expect(answer.goals.cost_bike_chf).toBe(-1);
    expect(answer.name).toBe('Cheaper');
    expect(answer.rules.some((rule) => !rule.passed)).toBe(true);
    expect(await gateway.get('geneva-3km.v1.D')).toEqual(answer);
  });

  it('refuses a run of a draft that breaks a rule and seals one that does not', async () => {
    const { gateway, versions } = fakePricing([
      samplePricingDraft({ goals: { max_displayed_options: 0 } }),
    ]);
    expect((await gateway.run('geneva-3km.v1.D')).kind).toBe('refused');
    await gateway.patch('geneva-3km.v1.D', { max_displayed_options: 5 });

    expect(await gateway.run('geneva-3km.v1.D')).toEqual({
      kind: 'queued',
      runId: 'run-pricing-D',
    });
    expect(versions()[0]).toMatchObject({ status: 'sealed', state: 'queued' });
    await expect(gateway.patch('geneva-3km.v1.D', { cost_bike_chf: 1 })).rejects.toThrow();
  });

  it('lists by instance version and discards', async () => {
    const { gateway } = fakePricing([
      samplePricingDraft(),
      samplePricingDraft({ id: 'x.v1.A', instanceVersionId: 'x.v1' }),
    ]);
    expect((await gateway.list('x.v1')).map((version) => version.id)).toEqual(['x.v1.A']);
    await gateway.discard('x.v1.A');
    expect(await gateway.list('x.v1')).toEqual([]);
    expect(await gateway.get('x.v1.A')).toBeNull();
  });

  it('answers a stored result for a finished version, none for the others, or what was supplied', async () => {
    const { gateway } = fakePricing([sampleSealedPricing(), samplePricingDraft()]);
    expect((await gateway.result('geneva-3km.v1.A'))?.pricingVersionId).toBe('geneva-3km.v1.A');
    expect(await gateway.result('geneva-3km.v1.D')).toBeNull();

    const own = samplePricingResult({ periodId: 'other' });
    const supplied = fakePricing([sampleSealedPricing()], {
      'geneva-3km.v1.A': own,
      'geneva-3km.v1.D': null,
    }).gateway;
    expect(await supplied.result('geneva-3km.v1.A')).toBe(own);
    expect(await supplied.result('geneva-3km.v1.D')).toBeNull();
  });

  it('samples a result whose prices take fewer travellers to the car than the flat price', () => {
    const { modelPrices, flat } = samplePricingResult().simulations;
    expect(modelPrices.travellers.car).toBeLessThan(flat.travellers.car);
  });

  it('answers the hub-pair and hub results of a finished version, none for the others, or what was supplied', async () => {
    const { gateway } = fakePricing([sampleSealedPricing(), samplePricingDraft()]);
    expect(await gateway.hubPairResults('geneva-3km.v1.A')).toEqual(sampleHubPairResults());
    expect(await gateway.hubResults('geneva-3km.v1.A')).toEqual(sampleHubResults());
    expect(await gateway.hubPairResults('geneva-3km.v1.D')).toBeNull();
    expect(await gateway.hubResults('geneva-3km.v1.D')).toBeNull();

    const supplied = fakePricing(
      [sampleSealedPricing()],
      {},
      {
        hubPairs: { 'geneva-3km.v1.A': [] },
        hubs: { 'geneva-3km.v1.A': null },
      },
    ).gateway;
    expect(await supplied.hubPairResults('geneva-3km.v1.A')).toEqual([]);
    expect(await supplied.hubResults('geneva-3km.v1.A')).toBeNull();
  });

  it('samples one priced pair with three options, one without rides and one with nothing offered', () => {
    const [priced, noRides, none] = sampleHubPairResults();
    expect(priced?.meanBikePrice).not.toBeNull();
    expect(priced?.options).toHaveLength(3);
    expect(noRides?.meanBikePrice).toBeNull();
    expect(noRides?.minBikePrice).not.toBeNull();
    expect(none?.minBikePrice).toBeNull();
    const hubs = new Set(sampleHubResults().map((hub) => hub.hubId));
    for (const pair of sampleHubPairResults()) {
      expect(hubs.has(pair.originHub) && hubs.has(pair.destinationHub)).toBe(true);
    }
  });

  it('answers the stored simulations of a finished version, none for a draft, or what was supplied', async () => {
    const { gateway } = fakePricing([sampleSealedPricing(), samplePricingDraft()]);
    expect(await gateway.simulations('geneva-3km.v1.A')).toEqual(sampleStoredSimulations());
    expect(await gateway.simulations('geneva-3km.v1.D')).toBeNull();

    const supplied = fakePricing(
      [sampleSealedPricing()],
      {},
      { simulations: { 'geneva-3km.v1.A': sampleStoredSimulations(true) } },
    ).gateway;
    const stored = (await supplied.simulations('geneva-3km.v1.A')) ?? [];
    expect(stored.filter((item) => !item.ruleCurrent)).toHaveLength(2);
  });
});
