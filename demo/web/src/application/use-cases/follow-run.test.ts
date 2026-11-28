import { describe, expect, it, vi } from 'vitest';
import { fakeCityInstances } from '../ports/fake-city-instance-gateway';
import { fakeRunGateway, sampleRunningBuild } from '../ports/fake-run-gateway';
import { cancelRun, loadActiveRuns, loadRun, runAgain } from './follow-run';

describe('following a run', () => {
  it('reads a run and the active runs through the gateway', async () => {
    const runs = fakeRunGateway([sampleRunningBuild]);

    expect(await loadRun({ runs }, 'run-2')).toBe(sampleRunningBuild);
    expect(await loadActiveRuns({ runs })).toEqual([sampleRunningBuild]);
  });

  it('cancels through the gateway, once', async () => {
    const runs = fakeRunGateway([sampleRunningBuild]);

    await cancelRun({ runs }, 'run-2');

    expect(runs.calls).toEqual(['cancel run-2']);
  });

  it('queues the build of a version again with the instance gateway', async () => {
    const build = vi.fn(() => Promise.resolve({ kind: 'queued' as const, runId: 'run-3' }));

    const answer = await runAgain({ cityInstances: fakeCityInstances({ build }) }, 'geneva-3km.v2');

    expect(answer).toEqual({ kind: 'queued', runId: 'run-3' });
    expect(build).toHaveBeenCalledWith('geneva-3km.v2');
  });
});
