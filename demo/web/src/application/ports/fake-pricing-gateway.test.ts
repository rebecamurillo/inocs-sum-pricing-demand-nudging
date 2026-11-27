import { describe, expect, it } from 'vitest';
import {
  fakePricing,
  pricingRulesOf,
  samplePricingDraft,
  samplePricingGoals,
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
});
