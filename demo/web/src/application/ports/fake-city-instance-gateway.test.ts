import { describe, expect, it } from 'vitest';
import { fakeCityInstances, sampleDraft, samplePlan } from './fake-city-instance-gateway';

describe('the fake city instance gateway', () => {
  it('answers the draft by its id and the writes with the sample draft', async () => {
    const gateway = fakeCityInstances();

    expect(await gateway.version('geneva-3km.v2')).toBe(sampleDraft);
    expect(await gateway.createInstance('A', 'd', { kind: 'package_defaults' })).toEqual({
      kind: 'created',
      version: sampleDraft,
    });
    expect(await gateway.createDraft('geneva-3km', 'geneva-3km.v1')).toEqual({
      kind: 'created',
      version: sampleDraft,
    });
    expect((await gateway.patch('geneva-3km.v2', { seed: 9 })).parameters.seed).toBe(9);
    await expect(gateway.discard('geneva-3km.v2')).resolves.toBeUndefined();
    expect(await gateway.build('geneva-3km.v2')).toEqual({ kind: 'queued', runId: 'run-2' });
  });

  it('deletes, or answers run_active for the ids it is told are active', async () => {
    const gateway = fakeCityInstances({}, new Set(['geneva-3km.v1', 'geneva-3km']));

    expect(await gateway.deleteVersion('geneva-3km.v2', false)).toEqual({ kind: 'deleted' });
    expect(await gateway.deleteVersion('geneva-3km.v1', false)).toEqual({ kind: 'run_active' });
    expect(await gateway.deleteInstance('geneva-2km', false)).toEqual({ kind: 'deleted' });
    expect(await gateway.deleteInstance('geneva-3km', false)).toEqual({ kind: 'run_active' });
  });

  it('builds a plan from the actions of its four steps', () => {
    const plan = samplePlan(['kept', 'rebuilt', 'rebuilt', 'rebuilt']);

    expect(plan.steps.map((step) => [step.number, step.action])).toEqual([
      [1, 'kept'],
      [2, 'rebuilt'],
      [3, 'rebuilt'],
      [4, 'rebuilt'],
    ]);
  });
});
