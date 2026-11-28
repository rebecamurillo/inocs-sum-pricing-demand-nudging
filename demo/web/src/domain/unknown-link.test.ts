import { describe, expect, it } from 'vitest';
import {
  instanceLabel,
  missingInstanceVersionLabel,
  missingPricingVersionLabel,
  nothingAtThisLink,
} from './unknown-link';

describe('the unknown-link sentence', () => {
  it('names the id and the instance version when the instance does not exist', () => {
    expect(
      nothingAtThisLink(instanceLabel(null, 'geneva-3km'), missingInstanceVersionLabel(1)),
    ).toBe('Nothing at this link: geneva-3km has no v1. It may have been deleted.');
  });

  it('names the instance and the pricing version when only the version is missing', () => {
    expect(
      nothingAtThisLink(
        instanceLabel('Geneva 3 km', 'geneva-3km'),
        missingPricingVersionLabel('C'),
      ),
    ).toBe('Nothing at this link: Geneva 3 km has no Version C. It may have been deleted.');
  });
});
