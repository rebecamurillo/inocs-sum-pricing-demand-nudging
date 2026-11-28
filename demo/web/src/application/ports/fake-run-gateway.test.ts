import { describe, expect, it } from 'vitest';
import { fakeRunGateway, sampleBuildSteps, sampleRunningBuild } from './fake-run-gateway';

describe('the fake run gateway', () => {
  it('answers a run by its id and rejects an unknown one', async () => {
    const gateway = fakeRunGateway([sampleRunningBuild]);

    expect(await gateway.get('run-2')).toBe(sampleRunningBuild);
    await expect(gateway.get('nope')).rejects.toThrow('No run nope.');
    expect(gateway.calls).toEqual(['get run-2', 'get nope']);
  });

  it('lists the active runs, the running one first', async () => {
    const queued = {
      ...sampleRunningBuild,
      id: 'run-3',
      state: 'queued' as const,
      queuePosition: 1,
    };
    const done = { ...sampleRunningBuild, id: 'run-1', state: 'succeeded' as const };
    const gateway = fakeRunGateway([queued, done, sampleRunningBuild]);

    expect((await gateway.listActive()).map((run) => run.id)).toEqual(['run-2', 'run-3']);
  });

  it('removes a queued run at once and leaves a running one running', async () => {
    const queued = {
      ...sampleRunningBuild,
      id: 'run-3',
      state: 'queued' as const,
      queuePosition: 1,
    };
    const gateway = fakeRunGateway([queued, sampleRunningBuild]);

    expect((await gateway.cancel('run-3')).state).toBe('cancelled');
    expect((await gateway.cancel('run-2')).state).toBe('running');
    await expect(gateway.cancel('nope')).rejects.toThrow('No run nope.');
    gateway.put({ ...sampleRunningBuild, state: 'failed' });
    expect((await gateway.get('run-2')).state).toBe('failed');
  });

  it('builds the steps of a build up to the running one', () => {
    expect(sampleBuildSteps(3).map((step) => step.state)).toEqual([
      'done',
      'done',
      'running',
      'pending',
    ]);
  });
});
