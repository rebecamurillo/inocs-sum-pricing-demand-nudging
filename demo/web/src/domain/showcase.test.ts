import { describe, expect, it } from 'vitest';
import { showcaseHolders } from './showcase';

describe('showcaseHolders', () => {
  it('derives the instance version and the city instance from a pricing version id', () => {
    expect(showcaseHolders('geneva-3km.v1.B')).toEqual({
      instanceVersionId: 'geneva-3km.v1',
      instanceId: 'geneva-3km',
    });
  });

  it('handles a lettered id with two letters and a later version', () => {
    expect(showcaseHolders('geneva-3km.v12.AB')).toEqual({
      instanceVersionId: 'geneva-3km.v12',
      instanceId: 'geneva-3km',
    });
  });
});
