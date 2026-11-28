import { describe, expect, it } from 'vitest';
import { fakePricing, sampleShowcase } from '../ports/fake-pricing-gateway';
import { loadShowcase } from './load-showcase';
import { setShowcase } from './set-showcase';

describe('setShowcase', () => {
  it('sends the version and the period, and the showcase answers them afterwards', async () => {
    const fake = fakePricing();

    await setShowcase(fake.gateway, 'geneva-3km.v1.C', 'monday-08');

    expect(fake.showcaseSet()).toEqual([
      { pricingVersionId: 'geneva-3km.v1.C', periodId: 'monday-08' },
    ]);
    const showcase = await loadShowcase(fake.gateway);
    expect(showcase?.pricingVersionId).toBe('geneva-3km.v1.C');
    expect(showcase?.letter).toBe('C');
  });

  it('lets the failure reach the caller and keeps the showcase', async () => {
    const fake = fakePricing([], {}, { showcase: sampleShowcase, setShowcaseFails: true });

    await expect(setShowcase(fake.gateway, 'geneva-3km.v1.C', 'monday-08')).rejects.toBeInstanceOf(
      Error,
    );
    await expect(loadShowcase(fake.gateway)).resolves.toEqual(sampleShowcase);
  });
});
