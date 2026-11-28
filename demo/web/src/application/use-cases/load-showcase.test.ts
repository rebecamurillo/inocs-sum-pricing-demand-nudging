import { describe, expect, it } from 'vitest';
import { fakePricing, sampleShowcase } from '../ports/fake-pricing-gateway';
import { loadShowcase } from './load-showcase';

describe('loadShowcase', () => {
  it('returns null when none is marked', async () => {
    await expect(loadShowcase(fakePricing().gateway)).resolves.toBeNull();
  });

  it('returns the marked result', async () => {
    const showcase = sampleShowcase;
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
