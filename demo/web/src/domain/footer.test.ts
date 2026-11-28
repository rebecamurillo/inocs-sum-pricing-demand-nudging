import { describe, expect, it } from 'vitest';
import {
  FUNDING_STATEMENT,
  MODEL_AUTHOR,
  RUN_UNMODIFIED_CONFIRMED,
  modelSourceLine,
} from './footer';

describe('the footer constants', () => {
  it('states the funding', () => {
    expect(FUNDING_STATEMENT).toBe(
      'Funded by the European Union under Horizon Europe, project SUM.',
    );
  });

  it('keeps "Run unmodified." off until it is confirmed', () => {
    expect(RUN_UNMODIFIED_CONFIRMED).toBe(false);
    const line = modelSourceLine(RUN_UNMODIFIED_CONFIRMED);
    expect(line).toEqual({
      before: 'Pricing model: ',
      author: MODEL_AUTHOR,
      authorIsPlaceholder: true,
      after: ', Inria INOCS.',
    });
  });

  it('adds "Run unmodified." when asked', () => {
    expect(modelSourceLine(true).after).toBe(', Inria INOCS. Run unmodified.');
  });
});
