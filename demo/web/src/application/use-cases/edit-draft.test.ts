import { describe, expect, it, vi } from 'vitest';
import {
  fakeCityInstances,
  patchedDraft,
  sampleDraft,
  samplePackageDefaults,
  sampleVersion,
} from '../ports/fake-city-instance-gateway';
import {
  createInstance,
  discardDraft,
  editAsNewVersion,
  openDraft,
  restoreDefaults,
  saveAndBuild,
  saveDraft,
  startFrom,
} from './edit-draft';

describe('edit-draft use cases', () => {
  it('creates an instance with a trimmed name', async () => {
    const createInstanceCall = vi.fn(() =>
      Promise.resolve({ kind: 'created' as const, version: sampleDraft }),
    );
    const cityInstances = fakeCityInstances({ createInstance: createInstanceCall });

    const result = await createInstance({ cityInstances }, '  Geneva 3 km ', 'ds-1', {
      kind: 'package_defaults',
    });

    expect(result.kind).toBe('created');
    expect(createInstanceCall).toHaveBeenCalledWith('Geneva 3 km', 'ds-1', {
      kind: 'package_defaults',
    });
  });

  it('opens a draft or the one the instance has', async () => {
    const createDraft = vi.fn(() =>
      Promise.resolve({ kind: 'draft_exists' as const, draftId: 'geneva-3km.v2' }),
    );
    const cityInstances = fakeCityInstances({ createDraft });

    expect(await editAsNewVersion({ cityInstances }, 'geneva-3km', 'geneva-3km.v1')).toEqual({
      kind: 'draft_exists',
      draftId: 'geneva-3km.v2',
    });
    expect(createDraft).toHaveBeenCalledWith('geneva-3km', 'geneva-3km.v1');
  });

  it('saves the changed values of a draft', async () => {
    const patch = vi.fn((_id: string, changes: Record<string, number>) =>
      Promise.resolve(patchedDraft(sampleDraft, changes)),
    );
    const cityInstances = fakeCityInstances({ patch });

    const saved = await saveDraft({ cityInstances }, 'geneva-3km.v2', { seed: 7 });

    expect(patch).toHaveBeenCalledWith('geneva-3km.v2', { seed: 7 });
    expect(saved.parameters.seed).toBe(7);
  });

  it('restores every parameter from the package defaults in one patch', async () => {
    const patch = vi.fn(() => Promise.resolve(sampleDraft));
    const cityInstances = fakeCityInstances({ patch });

    await restoreDefaults({ cityInstances }, sampleDraft);

    expect(patch).toHaveBeenCalledTimes(1);
    expect(patch).toHaveBeenCalledWith('geneva-3km.v2', {
      center_lat: samplePackageDefaults.centerLat,
      center_lon: samplePackageDefaults.centerLon,
      radius_m: 3000,
      clustering_threshold_m: 500,
      clustering_buffer_m: 100,
      min_od_distance_m: 500,
      min_demand: 10,
      max_demand: 70,
      fixed_capacity: 20,
      min_inventory_pct: 0,
      max_inventory_pct: 1,
      min_park_time_min: 1,
      max_park_time_min: 5,
      seed: 42,
    });
  });

  it('refuses to restore while the defaults are not known', async () => {
    const cityInstances = fakeCityInstances();

    await expect(
      restoreDefaults({ cityInstances }, { ...sampleDraft, packageDefaults: null }),
    ).rejects.toThrow('package defaults are not known');
  });

  it('starts from a saved version by patching every parameter to its values', async () => {
    const patch = vi.fn((_id: string, changes: Record<string, number>) =>
      Promise.resolve(patchedDraft(sampleDraft, changes)),
    );
    const cityInstances = fakeCityInstances({ patch });

    await startFrom({ cityInstances }, sampleDraft, { kind: 'copy', versionId: sampleVersion.id });

    expect(patch).toHaveBeenCalledWith(
      'geneva-3km.v2',
      expect.objectContaining({ min_od_distance_m: 900, max_inventory_pct: 100, seed: 42 }),
    );
    expect(Object.keys(patch.mock.calls[0]?.[1] ?? {})).toHaveLength(14);
  });

  it('starts from the package defaults like a restore, and fails for an unknown version', async () => {
    const patch = vi.fn(() => Promise.resolve(sampleDraft));
    const cityInstances = fakeCityInstances({ patch });

    await startFrom({ cityInstances }, sampleDraft, { kind: 'package_defaults' });
    expect(patch).toHaveBeenCalledWith(
      'geneva-3km.v2',
      expect.objectContaining({ min_od_distance_m: 500 }),
    );
    await expect(
      startFrom({ cityInstances }, sampleDraft, { kind: 'copy', versionId: 'nope.v1' }),
    ).rejects.toThrow('nope.v1');
  });

  it('discards a draft', async () => {
    const discard = vi.fn(() => Promise.resolve());
    const cityInstances = fakeCityInstances({ discard });

    await discardDraft({ cityInstances }, 'geneva-3km.v2');

    expect(discard).toHaveBeenCalledWith('geneva-3km.v2');
  });

  it('builds only after the autosave was flushed', async () => {
    const order: string[] = [];
    const build = vi.fn(() => {
      order.push('build');
      return Promise.resolve({ kind: 'queued' as const, runId: 'run-2' });
    });
    const cityInstances = fakeCityInstances({ build });
    const flush = () =>
      new Promise<void>((resolve) => {
        setTimeout(() => {
          order.push('flushed');
          resolve();
        }, 5);
      });

    const queued = await saveAndBuild({ cityInstances }, 'geneva-3km.v2', flush);

    expect(queued).toEqual({ kind: 'queued', runId: 'run-2' });
    expect(order).toEqual(['flushed', 'build']);
  });

  it('does not build when the flush fails', async () => {
    const build = vi.fn(() => Promise.resolve({ kind: 'queued' as const, runId: 'r' }));
    const cityInstances = fakeCityInstances({ build });

    await expect(
      saveAndBuild({ cityInstances }, 'a.v2', () => Promise.reject(new Error('patch failed'))),
    ).rejects.toThrow('patch failed');
    expect(build).not.toHaveBeenCalled();
  });

  it('opens the new draft, or the existing one and says it existed', async () => {
    const created = fakeCityInstances();
    expect(await openDraft({ cityInstances: created }, 'geneva-3km', 'geneva-3km.v1')).toEqual({
      version: sampleDraft,
      existed: false,
    });

    const exists = fakeCityInstances({
      createDraft: () => Promise.resolve({ kind: 'draft_exists', draftId: 'geneva-3km.v2' }),
    });
    expect(await openDraft({ cityInstances: exists }, 'geneva-3km', 'geneva-3km.v1')).toEqual({
      version: sampleDraft,
      existed: true,
    });

    const gone = fakeCityInstances({
      createDraft: () => Promise.resolve({ kind: 'draft_exists', draftId: 'x.v9' }),
    });
    await expect(openDraft({ cityInstances: gone }, 'geneva-3km', 'geneva-3km.v1')).rejects.toThrow(
      'x.v9',
    );
  });
});
