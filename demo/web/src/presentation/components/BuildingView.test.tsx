import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { CityInstanceGateway } from '../../application/ports/city-instance-gateway';
import {
  fakeCityInstances,
  sampleMenu,
  samplePlan,
  sampleVersion,
} from '../../application/ports/fake-city-instance-gateway';
import {
  fakeRunGateway,
  sampleBuildSteps,
  sampleRunningBuild,
  sampleStep,
  type FakeRunGateway,
} from '../../application/ports/fake-run-gateway';
import type { Gateways } from '../../application/ports/gateways';
import type { InstanceMenuEntry, InstanceVersion } from '../../domain/city-instance';
import type { Run } from '../../domain/run';
import { GatewaysProvider } from '../hooks/gateways';
import { fakeMapFactory, installBrowserStubs, type FakeMap } from '../map/fake-map';
import { MapFactoryProvider, MapProvider } from '../map/MapContext';
import { MapPane } from '../map/MapPane';
import { InstanceView } from './InstanceView';

const T0 = new Date('2026-11-27T10:00:00Z');

const building: InstanceVersion = {
  ...sampleVersion,
  id: 'geneva-3km.v2',
  number: 2,
  basedOnId: 'geneva-3km.v1',
  state: 'building',
  buildRunId: 'run-2',
  counts: null,
  routes: null,
  changes: [{ parameter: 'radius_m', before: 3000, after: 2000 }],
  buildPlan: {
    ...samplePlan(['kept', 'rebuilt', 'rebuilt', 'rebuilt']),
    steps: samplePlan(['kept', 'rebuilt', 'rebuilt', 'rebuilt']).steps.map((step) =>
      step.step === 'routes' ? { ...step, lastDurationS: 61 } : step,
    ),
  },
};

const menu: InstanceMenuEntry[] = [
  {
    id: 'geneva-3km',
    name: 'Geneva 3 km',
    datasetId: 'geneva-2026-11-26',
    versions: [
      ...(sampleMenu[0]?.versions ?? []),
      {
        id: 'geneva-3km.v2',
        number: 2,
        status: 'sealed',
        state: 'building',
        pricingVersionCount: 0,
      },
    ],
  },
];

/** A run whose server clock follows the browser's: `age` seconds after it started when read. */
function liveRun(base: Run, age: number): Run {
  return {
    ...base,
    startedAt: new Date(Date.now() - age * 1000),
    serverTime: new Date(Date.now()),
    steps: base.steps.map((step) =>
      step.state === 'running'
        ? { ...step, startedAt: new Date(Date.now() - (age - 60) * 1000) }
        : step,
    ),
    runner: { ...base.runner, lastHeartbeatAt: new Date(Date.now() - 1000) },
  };
}

function mount(options: {
  version?: InstanceVersion;
  run?: Run;
  runs?: FakeRunGateway;
  advancedView?: boolean;
  cityInstances?: Partial<CityInstanceGateway>;
}) {
  const version = options.version ?? building;
  const runs = options.runs ?? fakeRunGateway(options.run ? [options.run] : []);
  const gateways: Gateways = {
    systemStatus: { load: () => Promise.reject(new Error('not called')) },
    layoutPreferences: { load: vi.fn(), save: vi.fn() },
    cityDatasets: { list: () => Promise.resolve([]) },
    basemap: { exists: () => Promise.resolve(false), url: () => '' },
    cityInstances: fakeCityInstances({
      menu: () => Promise.resolve(menu),
      version: () => Promise.resolve(version),
      ...options.cityInstances,
    }),
    runs,
  };
  const { factory, maps } = fakeMapFactory();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <GatewaysProvider gateways={gateways}>
        <MapFactoryProvider factory={factory}>
          <MapProvider>
            <MapPane shown datasetId={null} />
            <InstanceView versionId={version.id} advancedView={options.advancedView ?? false} />
          </MapProvider>
        </MapFactoryProvider>
      </GatewaysProvider>
    </QueryClientProvider>,
  );
  const map = (): FakeMap => {
    const found = maps[0];
    if (found === undefined) throw new Error('no map');
    return found;
  };
  return { runs, map, client };
}

let stubs: ReturnType<typeof installBrowserStubs>;
beforeEach(() => {
  stubs = installBrowserStubs(false);
});
afterEach(() => {
  stubs.restore();
  vi.useRealTimers();
});

const found = (text: string | RegExp) => screen.findByText(text);
const featureCount = (map: FakeMap, id: string): number => {
  const source = map.sources.get(id) as { data: { features: unknown[] } } | undefined;
  return source?.data.features.length ?? -1;
};

describe('BuildingView · a running build', () => {
  it('shows the four steps with their counts, the routes bar and the building sentence', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    mount({ run: liveRun(sampleRunningBuild, 252) });

    expect(
      await found(
        'Building for 4 min 12 s. It continues if you open another page; v1 and its pricing versions stay available meanwhile.',
      ),
    ).toBeInTheDocument();
    const steps = within(screen.getByRole('list', { name: 'Build steps' })).getAllByRole(
      'listitem',
    );
    expect(steps.map((step) => step.textContent)).toEqual([
      '1 Area✓ 30 stops and platforms · 12 bike stations',
      '2 Hubs✓ 6 hubs',
      '3 Routes — 12 of 48 hub pairs · 2 queries gave no route so far●3 min 12 sLast time on this instance: 1 min 1 s.',
      '4 Travellers and bikeswaiting',
    ]);
    const bar = screen.getByRole('progressbar', { name: 'Hub pairs routed' });
    expect(bar).toHaveAttribute('aria-valuenow', '12');
    expect(bar).toHaveAttribute('aria-valuemax', '48');
    expect(screen.getByRole('columnheader', { name: 'What v2 changes' })).toBeInTheDocument();
  });

  it('writes a kept step with where it was kept from', async () => {
    const steps = sampleBuildSteps(3).map((step) =>
      step.number === 1 ? { ...step, state: 'kept' as const } : step,
    );
    mount({ run: liveRun({ ...sampleRunningBuild, steps }, 10) });

    expect(
      await found(/^✓ kept from v1 · 30 stops and platforms · 12 bike stations$/),
    ).toBeVisible();
  });

  it('writes the same kept step without a version it is based on', async () => {
    const steps = sampleBuildSteps(3).map((step) =>
      step.number === 1 ? { ...step, state: 'kept' as const } : step,
    );
    mount({
      version: { ...building, basedOnId: null, changes: [] },
      run: liveRun({ ...sampleRunningBuild, steps }, 7),
    });

    expect(
      await found(
        /^✓ kept: already computed with the same inputs · 30 stops and platforms · 12 bike stations$/,
      ),
    ).toBeVisible();
    expect(
      screen.getByText('Building for 7 s. It continues if you open another page.'),
    ).toBeVisible();
    expect(screen.queryByRole('columnheader', { name: /What v/ })).not.toBeInTheDocument();
  });

  it('counts a single failed query in the singular and shows a step without progress', async () => {
    const steps = sampleBuildSteps(3).map((step) =>
      step.number === 3
        ? { ...step, progress: { done: 1, total: 2 }, counts: { queries_failed: 1 } }
        : step,
    );
    mount({ run: liveRun({ ...sampleRunningBuild, steps }, 10) });

    expect(await found('3 Routes — 1 of 2 hub pairs · 1 query gave no route so far')).toBeVisible();
  });

  it('ticks the clock each second from the server time', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const runs = fakeRunGateway();
    const startedAt = new Date(Date.now() - 252_000);
    runs.get = () => Promise.resolve({ ...liveRun(sampleRunningBuild, 252), startedAt });
    mount({ runs });
    await found(/^Building for 4 min 12 s/);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });

    expect(screen.getByText(/^Building for 4 min 1[45] s/)).toBeVisible();
  });

  it('polls the run every 2 s and reads the version again when a step changes', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const version = vi.fn(() => Promise.resolve(building));
    const { runs } = mount({
      run: liveRun(sampleRunningBuild, 5),
      cityInstances: { version },
    });
    await found(/^Building for/);
    const reads = () => runs.calls.filter((call) => call === 'get run-2').length;
    expect(reads()).toBe(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    await waitFor(() => {
      expect(reads()).toBe(2);
    });
    const before = version.mock.calls.length;

    runs.put({ ...liveRun(sampleRunningBuild, 9), steps: sampleBuildSteps(4) });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    await waitFor(() => {
      expect(version.mock.calls.length).toBeGreaterThan(before);
    });
    expect(await found('4 Travellers and bikes')).toBeVisible();
  });

  it('draws stations once step 1 is done, hubs once step 2 is and pair lines once step 3 is', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const stations = () =>
      Promise.resolve([{ id: 'p1', kind: 'pt' as const, lat: 46.2, lon: 6.1 }]);
    const routePairs = vi.fn(() => Promise.resolve([{ originHub: 'H1', destinationHub: 'H2' }]));
    const view = mount({
      run: liveRun({ ...sampleRunningBuild, steps: sampleBuildSteps(2) }, 5),
      cityInstances: { stations, hubPairs: () => Promise.resolve([]), routePairs },
    });
    await found(/^Building for/);
    act(() => {
      view.map().emitStyleReady();
    });

    await waitFor(() => {
      expect(featureCount(view.map(), 'l1-stops')).toBe(1);
    });
    expect(featureCount(view.map(), 'l1-hub-outlines')).toBe(0);
    expect(featureCount(view.map(), 'l1-hub-pairs')).toBe(0);

    view.runs.put(liveRun({ ...sampleRunningBuild, steps: sampleBuildSteps(3) }, 9));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    await waitFor(() => {
      expect(featureCount(view.map(), 'l1-hub-pairs')).toBe(0);
      expect(view.map().sources.has('l1-hub-outlines')).toBe(true);
    });
    expect(featureCount(view.map(), 'l1-stops')).toBe(1);

    view.runs.put(liveRun({ ...sampleRunningBuild, steps: sampleBuildSteps(4) }, 12));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    await waitFor(() => {
      expect(featureCount(view.map(), 'l1-hub-pairs')).toBe(1);
    });
  });
});

describe('BuildingView · a queued build', () => {
  const queued: Run = {
    ...sampleRunningBuild,
    state: 'queued',
    startedAt: null,
    queuePosition: 1,
    steps: sampleBuildSteps(5).map((step) => sampleStep({ step: step.step, number: step.number })),
  };
  const ahead: Run = {
    ...sampleRunningBuild,
    id: 'run-1',
    subject: { type: 'instance_version', id: 'geneva-3km.v1' },
  };

  it('writes the place in line, shows the steps as waiting and offers to remove it', async () => {
    mount({
      version: { ...building, state: 'queued' },
      runs: fakeRunGateway([ahead, queued]),
    });

    expect(
      await found(
        'Queued, 2nd in line: Geneva 3 km v1 is building. Runs go one at a time; this one starts when the run before it ends.',
      ),
    ).toBeVisible();
    expect(screen.getAllByText('waiting')).toHaveLength(4);
    expect(screen.queryByRole('button', { name: 'Cancel run' })).not.toBeInTheDocument();
    expect(screen.queryByText(/^Building for/)).not.toBeInTheDocument();
  });

  it('confirms the removal in place and cancels once', async () => {
    const user = userEvent.setup();
    const { runs } = mount({
      version: { ...building, state: 'queued' },
      runs: fakeRunGateway([ahead, queued]),
    });

    await user.click(await screen.findByRole('button', { name: 'Remove from the queue' }));

    expect(
      screen.getByText(
        'Cancel this run? Nothing has run yet. Geneva 3 km v2 stays in the menu as cancelled: you can run it again or edit it as a new version.',
      ),
    ).toBeVisible();
    expect(screen.getByRole('button', { name: 'Keep' })).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Remove from the queue' }));

    await waitFor(() => {
      expect(runs.calls.filter((call) => call === 'cancel run-2')).toHaveLength(1);
    });
  });

  it('shows no place in line while no run is running', async () => {
    mount({ version: { ...building, state: 'queued' }, runs: fakeRunGateway([queued]) });

    await screen.findAllByText('waiting');

    expect(screen.queryByText(/in line/)).not.toBeInTheDocument();
  });
});

describe('BuildingView · cancelling a running build', () => {
  it('asks in place, keeps running on "Keep running" and cancels once on "Cancel the run"', async () => {
    const user = userEvent.setup();
    const { runs } = mount({ run: liveRun(sampleRunningBuild, 5) });

    await user.click(await screen.findByRole('button', { name: 'Cancel run' }));
    const question =
      'Cancel this run? The running step stops and is not stored; steps already done are kept. Geneva 3 km v2 stays in the menu as cancelled: you can run it again or edit it as a new version.';
    expect(screen.getByText(question)).toBeVisible();

    await user.click(screen.getByRole('button', { name: 'Keep running' }));
    expect(screen.queryByText(question)).not.toBeInTheDocument();
    expect(runs.calls).not.toContain('cancel run-2');

    await user.click(screen.getByRole('button', { name: 'Cancel run' }));
    await user.click(screen.getByRole('button', { name: 'Cancel the run' }));

    await waitFor(() => {
      expect(runs.calls.filter((call) => call === 'cancel run-2')).toHaveLength(1);
    });
    await waitFor(() => {
      expect(screen.queryByText(question)).not.toBeInTheDocument();
    });
  });
});

describe('BuildingView · a runner that stopped', () => {
  it('stops the clock and says when the runner last answered', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const heartbeat = new Date(2026, 10, 27, 10, 42);
    const silent: Run = {
      ...liveRun(sampleRunningBuild, 252),
      runner: { alive: false, lastHeartbeatAt: heartbeat },
    };
    mount({ run: silent });

    expect(
      await found(
        'The runner has not answered since 10:42. The run is kept and starts again when the runner is back (once).',
      ),
    ).toBeVisible();
    expect(screen.getByText(/^Building for 4 min 12 s/)).toBeVisible();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(screen.getByText(/^Building for 4 min 12 s/)).toBeVisible();
  });

  it('says a run was queued again after a stop, with its attempt', async () => {
    mount({ run: liveRun({ ...sampleRunningBuild, attempt: 2 }, 20) });

    expect(
      await found(
        'The runner stopped during Routes. The run was queued again (2nd attempt): Routes starts again from the beginning; steps before it are kept.',
      ),
    ).toBeVisible();
  });
});

describe('BuildingView · a failed build', () => {
  const failedRun = (code: string, reason = 'Boom: it broke'): Run => ({
    ...sampleRunningBuild,
    state: 'failed',
    finishedAt: T0,
    steps: sampleBuildSteps(3).map((step) =>
      step.number === 3 ? { ...step, state: 'failed' as const, progress: null } : step,
    ),
    failure: { step: 'routes', code, reason },
  });
  const failed: InstanceVersion = { ...building, state: 'failed' };

  it.each([
    ['trip_planner_unreachable', 'the trip planner did not answer'],
    [
      'no_public_transport',
      'the trip planner found no public transport route for any hub pair; the routing date, Monday 10 March 2025, may be outside the timetable (see City data)',
    ],
    [
      'instance_unbalanced',
      "the model's package could not balance the bike options of this instance",
    ],
    ['stage_error', "an error stopped the step. The details are in the run's log."],
    ['killed', 'the process was stopped by the system; the machine may be out of memory'],
    ['interrupted', 'the run was interrupted twice by a stop of the runner'],
    ['timetable_mismatch', "the trip planner's timetable is not the city data's timetable"],
  ])('writes the reason of %s', async (code, reason) => {
    mount({ version: failed, run: failedRun(code) });

    expect(
      await found(`✕ Routes failed: ${reason.replace(/\.$/, '')}. Steps before it are kept.`),
    ).toBeVisible();
    expect(screen.getByRole('button', { name: 'Run again from Routes' })).toBeVisible();
    expect(screen.getByText('✓ 30 stops and platforms · 12 bike stations')).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Cancel run' })).not.toBeInTheDocument();
  });

  it('shows the stored reason of a code it does not know', async () => {
    mount({ version: failed, run: failedRun('something_new', 'It broke somewhere') });

    expect(
      await found('✕ Routes failed: It broke somewhere. Steps before it are kept.'),
    ).toBeVisible();
  });

  it('shows the stored reason and the log link only with the Advanced view', async () => {
    mount({
      version: failed,
      run: failedRun('stage_error', 'ValueError: bad file'),
      advancedView: true,
    });

    expect(await found(/ValueError: bad file/)).toBeVisible();
    const link = screen.getByRole('link', { name: "Open the run's log" });
    expect(link).toHaveAttribute('href', '/api/v1/runs/run-2/log');
    expect(link).toHaveAttribute('target', '_blank');
  });

  it('hides them without it', async () => {
    mount({ version: failed, run: failedRun('stage_error', 'ValueError: bad file') });
    await found(/^✕ Routes failed/);

    expect(screen.queryByText(/ValueError/)).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: "Open the run's log" })).not.toBeInTheDocument();
  });

  it('queues the build again from the failed step and reads the version again', async () => {
    const user = userEvent.setup();
    const build = vi.fn(() => Promise.resolve({ kind: 'queued' as const, runId: 'run-3' }));
    mount({
      version: failed,
      run: failedRun('trip_planner_unreachable'),
      cityInstances: { build },
    });

    await user.click(await screen.findByRole('button', { name: 'Run again from Routes' }));

    await waitFor(() => {
      expect(build).toHaveBeenCalledWith('geneva-3km.v2');
    });
  });

  it('says why a build is refused', async () => {
    const user = userEvent.setup();
    const build = vi.fn(() =>
      Promise.resolve({ kind: 'refused' as const, detail: 'The trip planner is down.' }),
    );
    mount({
      version: failed,
      run: failedRun('trip_planner_unreachable'),
      cityInstances: { build },
    });

    await user.click(await screen.findByRole('button', { name: 'Run again from Routes' }));

    expect(await found('The trip planner is down.')).toBeVisible();
  });
});

describe('CancelledCard', () => {
  const cancelled: Run = {
    ...sampleRunningBuild,
    state: 'cancelled',
    finishedAt: new Date('2026-11-12T10:00:00Z'),
    steps: sampleBuildSteps(3).map((step) =>
      step.number === 3 ? { ...step, state: 'cancelled' as const } : step,
    ),
  };
  const version: InstanceVersion = { ...building, state: 'cancelled' };

  it('says where it stopped and offers "Run again" and "Edit as a new version"', async () => {
    mount({ version, run: cancelled });

    expect(
      await found('Run cancelled during Routes on 12 Nov 2026. Steps before it are kept.'),
    ).toBeVisible();
    expect(screen.getByRole('button', { name: 'Run again' })).toBeVisible();
    expect(screen.getByRole('button', { name: 'Edit as a new version' })).toBeVisible();
    expect(screen.queryByRole('button', { name: /Duplicate/ })).not.toBeInTheDocument();
  });

  it('names the first step for a run removed from the queue', async () => {
    const removed: Run = {
      ...cancelled,
      steps: sampleBuildSteps(5).map((step) =>
        sampleStep({ step: step.step, number: step.number }),
      ),
    };
    mount({ version, run: removed });

    expect(
      await found('Run cancelled during Area on 12 Nov 2026. Steps before it are kept.'),
    ).toBeVisible();
  });

  it('queues the build again', async () => {
    const user = userEvent.setup();
    const build = vi.fn(() => Promise.resolve({ kind: 'queued' as const, runId: 'run-3' }));
    mount({ version, run: cancelled, cityInstances: { build } });

    await user.click(await screen.findByRole('button', { name: 'Run again' }));

    await waitFor(() => {
      expect(build).toHaveBeenCalledWith('geneva-3km.v2');
    });
  });

  it('opens the draft with "Edit as a new version"', async () => {
    const user = userEvent.setup();
    const createDraft = vi.fn(() =>
      Promise.resolve({ kind: 'draft_exists' as const, draftId: 'geneva-3km.v3' }),
    );
    mount({ version, run: cancelled, cityInstances: { createDraft } });

    await user.click(await screen.findByRole('button', { name: 'Edit as a new version' }));

    await waitFor(() => {
      expect(createDraft).toHaveBeenCalledWith('geneva-3km', 'geneva-3km.v2');
    });
  });
});
