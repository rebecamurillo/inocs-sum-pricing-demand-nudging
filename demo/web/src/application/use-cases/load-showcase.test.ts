import { describe, expect, it } from 'vitest';
import { fakePricing } from '../ports/fake-pricing-gateway';
import { loadShowcase } from './load-showcase';

describe('loadShowcase', () => {
  it('returns null when none is marked', async () => {
    await expect(loadShowcase(fakePricing().gateway)).resolves.toBeNull();
  });

  it('returns the marked result', async () => {
    const showcase = {
      pricingVersionId: 'a.v1.A',
      periodId: 'p',
      instanceVersionId: 'a.v1',
      instanceVersionName: 'A',
      letter: 'A',
      markedAt: '2026-11-27T10:00:00Z',
    };
    await expect(loadShowcase(fakePricing([], {}, { showcase }).gateway)).resolves.toEqual(
      showcase,
    );
  });

  it('lets the failure reach the caller', async () => {
    const failure = new Error('down');
    await expect(loadShowcase(fakePricing([], {}, { showcase: failure }).gateway)).rejects.toBe(
      failure,
    );
  });
});
