import { describe, expect, it } from 'vitest';
import { fakePricing, sampleSealedPricing } from '../ports/fake-pricing-gateway';
import { compareVersions } from './compare-versions';

describe('comparing versions by their letters', () => {
  it('asks the gateway for the ids of the letters and answers its comparison', async () => {
    const { gateway } = fakePricing(
      ['A', 'B', 'C'].map((letter) =>
        sampleSealedPricing({ id: `geneva-3km.v1.${letter}`, letter, name: `Version ${letter}` }),
      ),
    );

    const answer = await compareVersions({ pricing: gateway }, 'geneva-3km.v1', ['C', 'A'], null);

    expect(answer.versions.map((version) => version.id)).toEqual([
      'geneva-3km.v1.A',
      'geneva-3km.v1.C',
    ]);
  });

  it('fails when a letter names no version', async () => {
    const { gateway } = fakePricing([sampleSealedPricing()]);
    await expect(
      compareVersions({ pricing: gateway }, 'geneva-3km.v1', ['A', 'Z'], null),
    ).rejects.toThrow('geneva-3km.v1.Z');
  });
});
