import { describe, expect, it, vi } from 'vitest';
import { fakeCityInstances } from '../ports/fake-city-instance-gateway';
import { deleteInstance, deleteVersion } from './delete-instance';

describe('delete-instance use cases', () => {
  it('deletes a version and an instance through the gateway', async () => {
    const deleteVersionCall = vi.fn(() => Promise.resolve({ kind: 'deleted' as const }));
    const deleteInstanceCall = vi.fn(() => Promise.resolve({ kind: 'deleted' as const }));
    const cityInstances = fakeCityInstances({
      deleteVersion: deleteVersionCall,
      deleteInstance: deleteInstanceCall,
    });

    expect(await deleteVersion({ cityInstances }, 'geneva-3km.v1', true)).toEqual({
      kind: 'deleted',
    });
    expect(await deleteInstance({ cityInstances }, 'geneva-3km', false)).toEqual({
      kind: 'deleted',
    });

    expect(deleteVersionCall).toHaveBeenCalledWith('geneva-3km.v1', true);
    expect(deleteInstanceCall).toHaveBeenCalledWith('geneva-3km', false);
  });

  it('passes run_active on', async () => {
    const cityInstances = fakeCityInstances({}, new Set(['geneva-3km.v1']));

    expect(await deleteVersion({ cityInstances }, 'geneva-3km.v1', false)).toEqual({
      kind: 'run_active',
    });
  });
});
