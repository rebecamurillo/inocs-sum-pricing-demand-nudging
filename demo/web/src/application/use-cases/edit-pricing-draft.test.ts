import { describe, expect, it, vi } from 'vitest';
import { fakePricing, samplePricingDraft } from '../ports/fake-pricing-gateway';
import {
  discardPricingDraft,
  duplicatePricingVersion,
  newPricingVersion,
  runPricingVersion,
  savePricingDraft,
} from './edit-pricing-draft';

describe('editing a pricing draft', () => {
  it('creates, saves and discards through the gateway', async () => {
    const { gateway, versions } = fakePricing();
    const gateways = { pricing: gateway };

    const draft = await newPricingVersion(gateways, 'geneva-3km.v1');
    const saved = await savePricingDraft(gateways, draft.id, { lowest_price_chf: 0.4 });
    expect(saved.goals.lowest_price_chf).toBe(0.4);

    await discardPricingDraft(gateways, draft.id);
    expect(versions()).toEqual([]);
  });

  it('duplicates a version into a draft of the same instance version with its goals', async () => {
    const source = samplePricingDraft({
      id: 'geneva-3km.v1.A',
      letter: 'A',
      goals: { pt_fare_chf: 2.4 },
    });
    const { gateway } = fakePricing([source]);

    const copy = await duplicatePricingVersion({ pricing: gateway }, source);

    expect(copy).toMatchObject({ letter: 'B', basedOnId: 'geneva-3km.v1.A', status: 'draft' });
    expect(copy.goals.pt_fare_chf).toBe(2.4);
  });

  it('flushes the autosave before it posts the run', async () => {
    const { gateway } = fakePricing([samplePricingDraft()]);
    const log: string[] = [];
    const run = vi.spyOn(gateway, 'run').mockImplementation(() => {
      log.push('run');
      return Promise.resolve({ kind: 'queued', runId: 'run-1' });
    });

    const queued = await runPricingVersion({ pricing: gateway }, 'geneva-3km.v1.D', () => {
      log.push('flush');
      return Promise.resolve();
    });

    expect(log).toEqual(['flush', 'run']);
    expect(queued).toEqual({ kind: 'queued', runId: 'run-1' });
    expect(run).toHaveBeenCalledWith('geneva-3km.v1.D');
  });

  it('does not post the run when the flush fails', async () => {
    const { gateway } = fakePricing([samplePricingDraft()]);
    const run = vi.spyOn(gateway, 'run');

    await expect(
      runPricingVersion({ pricing: gateway }, 'geneva-3km.v1.D', () =>
        Promise.reject(new Error('not saved')),
      ),
    ).rejects.toThrow('not saved');
    expect(run).not.toHaveBeenCalled();
  });
});
