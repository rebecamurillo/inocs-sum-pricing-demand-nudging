import { emptyTrips } from '../../application/ports/fake-trip-gateway';
import { QueryClient, QueryClientProvider, focusManager } from '@tanstack/react-query';
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { CityInstanceGateway } from '../../application/ports/city-instance-gateway';
import {
  fakeCityInstances,
  patchedDraft,
  sampleDraft,
  samplePlan,
  sampleMenu,
} from '../../application/ports/fake-city-instance-gateway';
import type { Gateways } from '../../application/ports/gateways';
import { fakePricingGateway } from '../../application/ports/fake-pricing-gateway';
import { fakeRunGateway } from '../../application/ports/fake-run-gateway';
import type {
  BuildPlan,
  InstanceMenuEntry,
  InstanceVersion,
  PlannedStep,
  RuleResult,
} from '../../domain/city-instance';
import { distanceM } from '../../domain/map';
import type { LabRoute } from '../../domain/route';
import { GatewaysProvider } from '../hooks/gateways';
import { fakeMapFactory, installBrowserStubs, type FakeMap } from '../map/fake-map';
import { MapFactoryProvider, MapProvider } from '../map/MapContext';
import { MapPane } from '../map/MapPane';
import { DraftForm } from './DraftForm';

function planStep(at: number): PlannedStep {
  const found = samplePlan().steps[at];
  if (found === undefined) throw new Error(`no step ${String(at)}`);
  return found;
}

const failedRule = (
  rule: string,
  a: RuleResult['values'][0],
  b: RuleResult['values'][1],
): RuleResult => ({ rule, passed: false, values: [a, b] });

const brokenMinTrip = failedRule(
  'min_trip_distance_above_grouping',
  { name: 'minimum trip distance', value: 500, unit: 'm' },
  { name: 'grouping distance', value: 600, unit: 'm' },
);

function withRules(rules: RuleResult[]): RuleResult[] {
  return sampleDraft.rules.map((rule) => rules.find((over) => over.rule === rule.rule) ?? rule);
}

const newInstance: InstanceVersion = {
  ...sampleDraft,
  id: 'geneva-3km.v1',
  number: 1,
  basedOnId: null,
  createdAt: new Date('2026-11-24T10:00:00Z'),
};

function menuFor(version: InstanceVersion): InstanceMenuEntry[] {
  const [first, second] = sampleMenu;
  const earlier = version.number > 1 ? (first?.versions ?? []) : [];
  return [
    {
      id: version.instanceId,
      name: 'Geneva 3 km',
      datasetId: 'geneva-2026-11-26',
      versions: [
        ...earlier,
        {
          id: version.id,
          number: version.number,
          status: 'draft',
          state: 'draft',
          pricingVersionCount: 0,
          pricingVersionLetters: [],
        },
      ],
    },
    ...(second === undefined ? [] : [second]),
  ];
}

function mount(
  version: InstanceVersion = sampleDraft,
  overrides: Partial<CityInstanceGateway> = {},
  onNavigate: (route: LabRoute) => void = () => undefined,
  notice: string | null = null,
) {
  const cityInstances = fakeCityInstances({
    menu: () => Promise.resolve(menuFor(version)),
    version: (id) => {
      if (id === version.id) return Promise.resolve(version);
      return Promise.resolve(
        id === 'geneva-3km.v1' || id === 'geneva-2km.v1' ? sampleVersionFor(id) : null,
      );
    },
    ...overrides,
  });
  const gateways: Gateways = {
    systemStatus: { load: () => Promise.reject(new Error('not called')) },
    layoutPreferences: { load: vi.fn(), save: vi.fn() },
    cityDatasets: {
      list: () =>
        Promise.resolve([
          {
            id: 'geneva-2026-11-26',
            centre: { lat: 46.2, lon: 6.14 },
            radiusM: 3000,
            availableArea: [6, 46, 6.3, 46.4] as const,
          },
        ]),
    },
    basemap: { exists: () => Promise.resolve(false), url: () => '' },
    cityInstances,
    runs: fakeRunGateway(),
    pricing: fakePricingGateway(),
    trips: emptyTrips,
  };
  const { factory, maps } = fakeMapFactory();
  const { unmount } = render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <GatewaysProvider gateways={gateways}>
        <MapFactoryProvider factory={factory}>
          <MapProvider>
            <MapPane shown datasetId={null} />
            <DraftForm
              versionId={version.id}
              advancedView={false}
              onNavigate={onNavigate}
              notice={notice}
            />
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
  return { map, unmount };
}

function sampleVersionFor(id: string): InstanceVersion {
  return { ...sampleDraft, id, number: 1, status: 'sealed', state: 'ready', basedOnId: null };
}

const input = (name: string) => screen.getByRole('textbox', { name });
const button = (name: string) => screen.getByRole('button', { name });

let stubs: ReturnType<typeof installBrowserStubs>;
beforeEach(() => {
  stubs = installBrowserStubs(false);
});
afterEach(() => {
  stubs.restore();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

/**
 * Fake timers that Testing Library's `asyncWrapper` can drain: it only advances timers it takes
 * for Jest's, so the shim names the one Vitest function it calls.
 */
function fakeTimers() {
  vi.useFakeTimers();
  vi.stubGlobal('jest', { advanceTimersByTime: (ms: number) => vi.advanceTimersByTime(ms) });
  return userEvent.setup({ advanceTimers: (ms) => vi.advanceTimersByTime(ms) });
}

async function ready() {
  await screen.findByRole('heading', { level: 2 });
}

describe('DraftForm · the edit form', () => {
  it('shows the heading without a number, the fields with their sentences and no Name', async () => {
    mount({ ...sampleDraft, parameters: { ...sampleDraft.parameters, maxInventoryPct: 1 } });
    await ready();

    expect(
      screen.getByRole('heading', { name: 'Geneva 3 km · new version (draft)' }),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText('Name')).not.toBeInTheDocument();
    expect(screen.queryByText(/Draft saved/)).not.toBeInTheDocument();
    expect(input('Centre latitude')).toHaveValue('46.2057');
    expect(input('Centre longitude')).toHaveValue('6.1489');
    expect(screen.getByText('Drag the centre on the map or type it.')).toBeInTheDocument();
    expect(input('Radius')).toHaveValue('3.0');
    expect(
      screen.getByText('From 1 to 5 km. A larger zone has more hubs and takes longer to build.'),
    ).toBeInTheDocument();
    expect(input('Grouping distance')).toHaveValue('500');
    expect(
      screen.getByText('Stops and stations closer than this form one hub.'),
    ).toBeInTheDocument();
    expect(input('Travellers per hub pair, lowest')).toHaveValue('10');
    expect(input('Travellers per hub pair, highest')).toHaveValue('70');
    // The package keeps a share of docks: the form writes it in percent.
    expect(input('Bikes at 08:00, highest')).toHaveValue('100');
    expect(screen.getAllByText('% of docks')).toHaveLength(2);
    expect(input('Random seed')).toHaveValue('42');
    expect(button('Save and build')).toBeInTheDocument();
    expect(button('Restore the package defaults')).toHaveAttribute(
      'title',
      "Sets every value of this draft back to the model package's default values. Nothing is saved as a version until Save and build.",
    );
    expect(button('Discard draft')).toBeInTheDocument();
  });

  it('writes the one-draft sentence it was opened with', async () => {
    mount(
      sampleDraft,
      {},
      () => undefined,
      'This instance already has a draft, started from v1 on 24 Nov. Continue it, or discard it first.',
    );
    await ready();

    expect(
      screen.getByText(
        'This instance already has a draft, started from v1 on 24 Nov. Continue it, or discard it first.',
      ),
    ).toBeInTheDocument();
  });

  it('lists every rule with its mark, the routing date on the Periods line', async () => {
    mount();
    await ready();

    const box = screen.getByRole('region', { name: 'Rules checked before saving' });
    const items = within(box).getAllByRole('listitem');
    expect(items).toHaveLength(9);
    expect(items[0]).toHaveTextContent(
      '✓Minimum trip distance is greater than the grouping distance',
    );
    expect(within(box).queryByText(/Routing date/)).not.toBeInTheDocument();
    expect(
      screen.getByText(
        'Routing date inside the timetable: Monday 10 March 2025 is within 15 Dec 2024 – 13 Dec 2025',
      ),
    ).toBeInTheDocument();
  });

  it('shows a changed value with the previous one struck through, the save box and what changes', async () => {
    const changed = {
      ...sampleDraft,
      parameters: { ...sampleDraft.parameters, clusteringThresholdM: 400 },
      changes: [{ parameter: 'clustering_threshold_m' as const, before: 500, after: 400 }],
      buildPlan: samplePlan(['kept', 'rebuilt', 'rebuilt', 'rebuilt']),
    };
    mount(changed);
    await ready();

    const grouping = screen.getByRole('group', { name: 'Grouping distance' });
    expect(within(grouping).getByText('500 m').tagName).toBe('S');
    expect(
      screen.getByText(
        'Saving creates Geneva 3 km v2. v1 and its 3 pricing versions stay as they are. Will rebuild: 2 Hubs, 3 Routes, 4 Travellers and bikes; step 1 is kept.',
      ),
    ).toBeInTheDocument();
    const table = screen.getByRole('table');
    expect(within(table).getByText('What v2 changes')).toBeInTheDocument();
    expect(within(table).getByText('Grouping distance')).toBeInTheDocument();
    expect(within(table).getByText('400 m')).toBeInTheDocument();
    expect(button('Save and build')).toBeEnabled();
  });

  it('adds the measured duration and a row per cause that is not a value', async () => {
    const plan: BuildPlan = {
      steps: [
        {
          ...planStep(0),
          action: 'rebuilt',
          lastDurationS: 60,
          causes: [{ kind: 'package', parameters: [] }],
        },
        {
          ...planStep(1),
          lastDurationS: 120,
          causes: [
            { kind: 'city_data', parameters: [] },
            { kind: 'trip_planner_graph', parameters: [] },
          ],
        },
        { ...planStep(2), lastDurationS: 180 },
        { ...planStep(3), lastDurationS: 180 },
      ],
      verdict: { allowed: true, reasons: [] },
    };
    mount({ ...sampleDraft, buildPlan: plan });
    await ready();

    expect(
      screen.getByText(
        /Will rebuild: 1 Area, 2 Hubs, 3 Routes, 4 Travellers and bikes\. Last build of this size: about 9 min\.$/,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText("The pricing model's package changed since v1: every step is rebuilt."),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "The trip planner's graph changed since v1: Routes and the steps after it are rebuilt.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText('New city data (bike stations fetched 10 Nov 2026): every step is rebuilt.'),
    ).toBeInTheDocument();
    expect(button('Save and build')).toBeEnabled();
  });

  it('disables the primary while nothing differs from the version it is based on', async () => {
    mount();
    await ready();

    expect(button('Save and build')).toBeDisabled();
    expect(screen.getByText('Nothing differs from v1 yet.')).toBeInTheDocument();
  });
});

describe('DraftForm · a broken rule', () => {
  it('names both values, turns the fields red and disables the primary', async () => {
    mount({ ...sampleDraft, rules: withRules([brokenMinTrip]) });
    await ready();

    expect(
      screen.getByText(
        'Minimum trip distance is greater than the grouping distance: now 500 m against 600 m',
      ),
    ).toBeInTheDocument();
    expect(input('Minimum trip distance')).toHaveAttribute('aria-invalid', 'true');
    expect(input('Grouping distance')).toHaveAttribute('aria-invalid', 'true');
    expect(input('Radius')).toHaveAttribute('aria-invalid', 'false');
    expect(button('Save and build')).toBeDisabled();
    expect(screen.getByText('One rule is not met.')).toBeInTheDocument();
  });

  it('shows ✕ on the centre rule and on the routing-date line', async () => {
    mount({
      ...sampleDraft,
      rules: withRules([
        failedRule(
          'centre_inside_area',
          { name: 'centre', value: '47, 6', unit: null },
          { name: 'available area', value: 'Geneva', unit: null },
        ),
        failedRule(
          'routing_date_inside_timetable',
          { name: 'routing date', value: '2025-03-10', unit: null },
          { name: 'timetable validity', value: 'x to y', unit: null },
        ),
      ]),
    });
    await ready();

    expect(
      screen.getByText(
        'The centre is inside the area of the Geneva data: now 47, 6 against Geneva',
      ),
    ).toBeInTheDocument();
    expect(input('Centre latitude')).toHaveAttribute('aria-invalid', 'true');
    expect(
      screen.getByText(
        'Routing date inside the timetable: now Monday 10 March 2025 against 15 Dec 2024 – 13 Dec 2025',
      ),
    ).toBeInTheDocument();
  });
});

describe('DraftForm · banners', () => {
  const changed = {
    parameters: { ...sampleDraft.parameters, seed: 7 },
    changes: [{ parameter: 'seed' as const, before: 42, after: 7 }],
  };
  const blocked = (component: 'runner' | 'tripPlanner' | 'cityData' | 'package') => ({
    ...sampleDraft,
    ...changed,
    buildPlan: {
      ...samplePlan(),
      verdict: { allowed: false, reasons: [{ component, reason: 'x' }] },
    },
  });

  it.each([
    ['runner', 'New builds are off: the runner is not running. Queued runs wait.'],
    [
      'tripPlanner',
      'This change rebuilds the routes, and the trip planner is not reachable. A change to the travellers and bikes only can still be built.',
    ],
    [
      'cityData',
      "No city data is imported yet. A city instance needs a timetable and bike stations; the maintainer imports Geneva's with one command (demo/README.md).",
    ],
    ['package', "New builds are off: the pricing model's package does not load on this machine."],
  ] as const)(
    'shows the %s banner, ending with the stored-results sentence, and disables the primary',
    async (component, sentence) => {
      mount(blocked(component));
      await ready();

      expect(screen.getByText(`${sentence} Stored results stay available.`)).toBeInTheDocument();
      expect(button('Save and build')).toBeDisabled();
      expect(screen.getByText(sentence)).toBeInTheDocument();
    },
  );
});

describe('DraftForm · autosave', () => {
  it('sends one patch 500 ms after the last change and shows when it was saved', async () => {
    const patch = vi.fn((_id: string, changes: Record<string, number>) =>
      Promise.resolve(patchedDraft(sampleDraft, changes)),
    );
    mount(sampleDraft, { patch });
    await ready();
    const user = fakeTimers();

    await user.clear(input('Grouping distance'));
    await user.type(input('Grouping distance'), '400');
    expect(patch).not.toHaveBeenCalled();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(499);
    });
    expect(patch).not.toHaveBeenCalled();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });

    expect(patch).toHaveBeenCalledTimes(1);
    expect(patch).toHaveBeenCalledWith('geneva-3km.v2', { clustering_threshold_m: 400 });
    expect(screen.getByText(/^Draft saved · \d{2}:\d{2}$/)).toBeInTheDocument();
  });

  it('writes the radius in km and sends metres, the bike shares in percent and sends shares', async () => {
    const patch = vi.fn((_id: string, changes: Record<string, number>) =>
      Promise.resolve(patchedDraft(sampleDraft, changes)),
    );
    mount(sampleDraft, { patch });
    await ready();
    const user = fakeTimers();

    await user.clear(input('Radius'));
    await user.type(input('Radius'), '3.5');
    await user.clear(input('Bikes at 08:00, highest'));
    await user.type(input('Bikes at 08:00, highest'), '80');
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });

    expect(patch).toHaveBeenCalledTimes(1);
    expect(patch).toHaveBeenCalledWith('geneva-3km.v2', { radius_m: 3500, max_inventory_pct: 0.8 });
  });

  it('keeps what is typed when the answer of an earlier patch arrives', async () => {
    let answer: (version: InstanceVersion) => void = () => undefined;
    const patch = vi.fn(
      () =>
        new Promise<InstanceVersion>((resolve) => {
          answer = resolve;
        }),
    );
    mount(sampleDraft, { patch });
    await ready();
    const user = fakeTimers();

    await user.clear(input('Random seed'));
    await user.type(input('Random seed'), '7');
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });
    await user.type(input('Random seed'), '5');
    await act(async () => {
      answer(patchedDraft(sampleDraft, { seed: 7 }));
      await Promise.resolve();
    });

    expect(input('Random seed')).toHaveValue('75');
  });

  it('shows the rules of the last answer', async () => {
    const patch = vi.fn(() =>
      Promise.resolve({ ...sampleDraft, rules: withRules([brokenMinTrip]) }),
    );
    mount(sampleDraft, { patch });
    await ready();
    const user = fakeTimers();

    await user.type(input('Random seed'), '1');
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });

    expect(
      await screen.findByText(
        /Minimum trip distance is greater than the grouping distance: now 500 m against 600 m/,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText('One rule is not met.')).toBeInTheDocument();
  });
});

describe('DraftForm · a read in flight', () => {
  it('does not let a read sent before a patch answer replace that answer', async () => {
    let reads = 0;
    let staleRead: () => void = () => undefined;
    const version = vi.fn((id: string) => {
      reads += 1;
      if (id !== sampleDraft.id) return Promise.resolve(null);
      if (reads === 1) return Promise.resolve(sampleDraft);
      // A refetch on window focus that reads the draft before the patch below lands.
      return new Promise<InstanceVersion>((resolve) => {
        staleRead = () => {
          resolve({ ...sampleDraft, rules: withRules([brokenMinTrip]) });
        };
      });
    });
    let answer: () => void = () => undefined;
    const patch = vi.fn(
      (_id: string, changes: Record<string, number>) =>
        new Promise<InstanceVersion>((resolve) => {
          answer = () => {
            resolve(patchedDraft(sampleDraft, changes));
          };
        }),
    );
    mount(sampleDraft, { version, patch });
    await ready();
    const user = fakeTimers();

    await user.type(input('Random seed'), '1');
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });
    expect(patch).toHaveBeenCalledTimes(1);
    await act(async () => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(reads).toBe(2);
    await act(async () => {
      answer();
      await vi.advanceTimersByTimeAsync(0);
    });
    await act(async () => {
      staleRead();
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(screen.getByText(/^Draft saved/)).toBeInTheDocument();
    expect(screen.queryByText('One rule is not met.')).not.toBeInTheDocument();
    focusManager.setFocused(undefined);
  });
});

describe('DraftForm · restore, discard and build', () => {
  it('restores every parameter with one patch and no confirmation', async () => {
    const patch = vi.fn(() => Promise.resolve(sampleDraft));
    mount({ ...sampleDraft, parameters: { ...sampleDraft.parameters, seed: 7 } }, { patch });
    await ready();

    await userEvent.setup().click(button('Restore the package defaults'));

    expect(patch).toHaveBeenCalledTimes(1);
    const sent = patch.mock.calls[0] as unknown as [string, Record<string, number>];
    expect(sent[0]).toBe('geneva-3km.v2');
    expect(Object.keys(sent[1])).toHaveLength(14);
    expect(sent[1]).toMatchObject({ seed: 42, min_od_distance_m: 500, max_inventory_pct: 1 });
    await waitFor(() => {
      expect(input('Random seed')).toHaveValue('42');
    });
    expect(screen.queryByText(/Discard this draft/)).not.toBeInTheDocument();
  });

  it('asks before it discards, keeps on "Keep", and opens the based-on version after confirming', async () => {
    const discard = vi.fn(() => Promise.resolve());
    const onNavigate = vi.fn();
    mount(sampleDraft, { discard }, onNavigate);
    await ready();
    const user = userEvent.setup();

    await user.click(button('Discard draft'));
    expect(
      screen.getByText('Discard this draft? Its values are removed; v1 stays as it is.'),
    ).toBeInTheDocument();
    await user.click(button('Keep'));
    expect(screen.queryByText(/Discard this draft/)).not.toBeInTheDocument();
    expect(discard).not.toHaveBeenCalled();

    await user.click(button('Discard draft'));
    await user.click(button('Discard draft'));

    await waitFor(() => {
      expect(discard).toHaveBeenCalledWith('geneva-3km.v2');
    });
    await waitFor(() => {
      expect(onNavigate).toHaveBeenCalledWith({
        kind: 'instance',
        instance: { instanceId: 'geneva-3km', version: 1 },
        period: null,
      });
    });
  });

  it('flushes the pending patch before it posts the build, then opens the version', async () => {
    const order: string[] = [];
    const patch = vi.fn((_id: string, changes: Record<string, number>) => {
      order.push('patch');
      return Promise.resolve(patchedDraft(sampleDraft, changes));
    });
    const build = vi.fn(() => {
      order.push('build');
      return Promise.resolve({ kind: 'queued' as const, runId: 'run-2' });
    });
    const onNavigate = vi.fn();
    mount(
      {
        ...sampleDraft,
        changes: [{ parameter: 'seed', before: 42, after: 7 }],
        buildPlan: samplePlan(),
      },
      { patch, build },
      onNavigate,
    );
    await ready();
    const user = fakeTimers();

    await user.type(input('Random seed'), '1');
    await user.click(button('Save and build'));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10);
    });

    expect(onNavigate).toHaveBeenCalled();
    expect(order).toEqual(['patch', 'build']);
    expect(build).toHaveBeenCalledWith('geneva-3km.v2');
    expect(onNavigate).toHaveBeenCalledWith({
      kind: 'instance',
      instance: { instanceId: 'geneva-3km', version: 2 },
      period: null,
    });
  });

  it('shows a failed patch and sends its change again before the build', async () => {
    const order: string[] = [];
    let failNext = true;
    const patch = vi.fn((_id: string, changes: Record<string, number>) => {
      order.push(`patch ${JSON.stringify(changes)}`);
      if (failNext) {
        failNext = false;
        return Promise.reject(new Error('The API could not be reached'));
      }
      return Promise.resolve(patchedDraft(sampleDraft, changes));
    });
    const build = vi.fn(() => {
      order.push('build');
      return Promise.resolve({ kind: 'queued' as const, runId: 'run-2' });
    });
    mount(
      {
        ...sampleDraft,
        changes: [{ parameter: 'seed', before: 42, after: 7 }],
        buildPlan: samplePlan(),
      },
      { patch, build },
    );
    await ready();
    const user = fakeTimers();

    await user.clear(input('Random seed'));
    await user.type(input('Random seed'), '9');
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });
    expect(screen.getByText('The API could not be reached')).toBeInTheDocument();

    await user.click(button('Save and build'));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10);
    });

    expect(order).toEqual(['patch {"seed":9}', 'patch {"seed":9}', 'build']);
    expect(screen.queryByText('The API could not be reached')).not.toBeInTheDocument();
  });

  it('takes no more changes once the build is sent', async () => {
    const patch = vi.fn((_id: string, changes: Record<string, number>) =>
      Promise.resolve(patchedDraft(sampleDraft, changes)),
    );
    const build = vi.fn(() => new Promise<never>(() => undefined));
    mount(
      {
        ...sampleDraft,
        changes: [{ parameter: 'seed', before: 42, after: 7 }],
        buildPlan: samplePlan(),
      },
      { patch, build },
    );
    await ready();
    const user = fakeTimers();

    await user.click(button('Save and build'));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10);
    });
    expect(build).toHaveBeenCalledTimes(1);
    await user.type(input('Random seed'), '1');
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });

    expect(input('Random seed')).toHaveAttribute('readonly');
    expect(patch).not.toHaveBeenCalled();
  });

  it('shows the detail of a refused build as the primary note', async () => {
    const build = vi.fn(() =>
      Promise.resolve({ kind: 'refused' as const, detail: 'A build of this version is queued.' }),
    );
    mount(
      {
        ...sampleDraft,
        changes: [{ parameter: 'seed', before: 42, after: 7 }],
        buildPlan: samplePlan(),
      },
      { build },
    );
    await ready();

    await userEvent.setup().click(button('Save and build'));

    expect(await screen.findByText('A build of this version is queued.')).toBeInTheDocument();
  });
});

describe('DraftForm · the new-instance form', () => {
  it('shows Name read-only, City data, Start from, the groups, the rules and no save box', async () => {
    mount(newInstance);
    await ready();

    expect(
      screen.getByRole('heading', { name: 'Geneva 3 km · new version (draft)' }),
    ).toBeInTheDocument();
    expect(input('Name')).toHaveAttribute('readonly');
    expect(input('Name')).toHaveValue('Geneva 3 km');
    const city = screen.getByRole('combobox', { name: 'City data' });
    expect(
      within(city).getByRole('option', { name: 'Geneva · tpg + Donkey Republic' }),
    ).toBeInTheDocument();
    expect(
      within(city).getByRole('option', { name: 'Another city · not in this version' }),
    ).toBeDisabled();
    expect(
      screen.getByText(
        'A city needs a public transport timetable (GTFS) and a shared-bike station feed (GBFS).',
      ),
    ).toBeInTheDocument();
    const start = screen.getByRole('combobox', { name: 'Start from' });
    expect(start).toHaveValue('defaults');
    expect(
      within(start).getByRole('option', { name: "The model package's default values" }),
    ).toBeInTheDocument();
    expect(
      await within(start).findByRole('option', { name: 'A copy of Geneva 2 km v1' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Rules checked before saving' })).toBeInTheDocument();
    expect(screen.queryByText(/Saving creates/)).not.toBeInTheDocument();
    expect(screen.queryByText(/What v1 changes/)).not.toBeInTheDocument();
    expect(button('Save as v1 and build')).toBeEnabled();
    expect(button('Restore the package defaults')).toBeInTheDocument();
  });

  it('patches every parameter to the source version when another Start from is chosen', async () => {
    const patch = vi.fn((_id: string, changes: Record<string, number>) =>
      Promise.resolve(patchedDraft(newInstance, changes)),
    );
    mount(newInstance, { patch });
    await ready();
    const start = screen.getByRole('combobox', { name: 'Start from' });
    await within(start).findByRole('option', { name: 'A copy of Geneva 2 km v1' });

    await userEvent.setup().selectOptions(start, 'A copy of Geneva 2 km v1');

    await waitFor(() => {
      expect(patch).toHaveBeenCalledTimes(1);
    });
    const sent = patch.mock.calls[0] as unknown as [string, Record<string, number>];
    expect(Object.keys(sent[1])).toHaveLength(14);
    expect(sent[1]).toMatchObject({ min_od_distance_m: 900 });
  });

  it('keeps a value typed while the Start from answer is on its way', async () => {
    let answer: () => void = () => undefined;
    const patch = vi.fn(
      (_id: string, changes: Record<string, number>) =>
        new Promise<InstanceVersion>((resolve) => {
          answer = () => {
            resolve(patchedDraft(newInstance, changes));
          };
        }),
    );
    mount(newInstance, { patch });
    await ready();
    const start = screen.getByRole('combobox', { name: 'Start from' });
    await within(start).findByRole('option', { name: 'A copy of Geneva 2 km v1' });
    const user = userEvent.setup();
    await user.selectOptions(start, 'A copy of Geneva 2 km v1');
    await waitFor(() => {
      expect(patch).toHaveBeenCalledTimes(1);
    });

    await user.clear(input('Random seed'));
    await user.type(input('Random seed'), '9');
    await act(async () => {
      answer();
      await Promise.resolve();
    });

    expect(input('Random seed')).toHaveValue('9');
    expect(input('Minimum trip distance')).toHaveValue('900');
  });

  it('reads "The model package\'s default values" again after a restore', async () => {
    const patch = vi.fn(() => Promise.resolve(newInstance));
    mount({ ...newInstance, basedOnId: 'geneva-2km.v1' }, { patch });
    await ready();
    const start = screen.getByRole('combobox', { name: 'Start from' });
    await within(start).findByRole('option', { name: 'A copy of Geneva 2 km v1' });
    expect(start).toHaveValue('copy:geneva-2km.v1');

    await userEvent.setup().click(button('Restore the package defaults'));

    expect(start).toHaveValue('defaults');
  });

  it('words the discard question without a version, and opens the empty Lab', async () => {
    const discard = vi.fn(() => Promise.resolve());
    const onNavigate = vi.fn();
    mount(newInstance, { discard }, onNavigate);
    await ready();
    const user = userEvent.setup();

    await user.click(button('Discard draft'));
    expect(screen.getByText('Discard this draft? Its values are removed.')).toBeInTheDocument();
    await user.click(button('Discard draft'));

    await waitFor(() => {
      expect(onNavigate).toHaveBeenCalledWith({ kind: 'lab', period: null });
    });
  });
});

describe('DraftForm · the map', () => {
  const eastOf = (metres: number) => ({
    lat: 46.2057,
    lon: 6.1489 + metres / (111_195 * Math.cos((46.2057 * Math.PI) / 180)),
  });

  it('draws the study circle with two draggable handles and the processing-time sentence', async () => {
    const { map } = mount();
    await ready();
    act(() => {
      map().emitStyleReady();
    });

    await waitFor(() => {
      expect(map().markers).toHaveLength(2);
    });
    expect(map().layers.map((layer) => layer.id)).toEqual([
      'l1-study-circle',
      'l1-hub-pairs',
      'l1-hub-outlines',
      'l1-stops',
      'l1-bike-stations',
    ]);
    expect(map().markers.every((marker) => marker.options.draggable)).toBe(true);
    expect(screen.getByText(/A larger zone has more hubs/)).toBeInTheDocument();
  });

  it('follows a drag of the centre in the fields and patches it like a typed change', async () => {
    const patch = vi.fn((_id: string, changes: Record<string, number>) =>
      Promise.resolve(patchedDraft(sampleDraft, changes)),
    );
    const { map } = mount(sampleDraft, { patch });
    await ready();
    act(() => {
      map().emitStyleReady();
    });
    await waitFor(() => {
      expect(map().markers).toHaveLength(2);
    });
    vi.useFakeTimers();

    act(() => {
      map().markers[0]?.drag({ lat: 46.21, lon: 6.15 });
    });

    expect(input('Centre latitude')).toHaveValue('46.21');
    expect(input('Centre longitude')).toHaveValue('6.15');
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });
    expect(patch).toHaveBeenCalledTimes(1);
    expect(patch).toHaveBeenCalledWith('geneva-3km.v2', { center_lat: 46.21, center_lon: 6.15 });
  });

  it('follows a drag of the radius handle in km', async () => {
    const { map } = mount();
    await ready();
    act(() => {
      map().emitStyleReady();
    });
    await waitFor(() => {
      expect(map().markers).toHaveLength(2);
    });

    act(() => {
      map().markers[1]?.drag(eastOf(4060));
    });

    expect(input('Radius')).toHaveValue('4.1');
    const edge = map().markers[1];
    expect(
      distanceM({ lat: 46.2057, lon: 6.1489 }, edge?.position ?? { lat: 0, lon: 0 }),
    ).toBeCloseTo(4100, -1);
  });

  it('removes the handles and the circle when the form closes', async () => {
    const { map, unmount } = mount();
    await ready();
    act(() => {
      map().emitStyleReady();
    });
    await waitFor(() => {
      expect(map().markers).toHaveLength(2);
    });

    unmount();

    expect(map().markers.every((marker) => marker.removed)).toBe(true);
    expect(map().layers).toEqual([]);
  });
});
