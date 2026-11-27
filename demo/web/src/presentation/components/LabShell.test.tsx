import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { CityInstanceGateway } from '../../application/ports/city-instance-gateway';
import {
  emptyCityInstances,
  fakeCityInstances,
  sampleDraft,
  sampleMenu,
  sampleVersion,
} from '../../application/ports/fake-city-instance-gateway';
import type { Gateways } from '../../application/ports/gateways';
import {
  fakeRunGateway,
  sampleBuildSteps,
  sampleRunningBuild,
} from '../../application/ports/fake-run-gateway';
import type { RunGateway } from '../../application/ports/run-gateway';
import { DEFAULT_LAYOUT, type LayoutPreferencesValue } from '../../domain/layout';
import type { CityDataset } from '../../domain/map';
import type { SystemStatus } from '../../domain/system-status';
import { GatewaysProvider } from '../hooks/gateways';
import { INSTANCE_MENU_KEY } from '../hooks/useCityInstances';
import { fakeMapFactory, installBrowserStubs } from '../map/fake-map';
import { MapFactoryProvider } from '../map/MapContext';
import { LabShell } from './LabShell';

const allowed = { allowed: true, reasons: [] };
const status: SystemStatus = {
  components: [],
  canBuildInstances: allowed,
  canRunPricing: allowed,
  canSimulate: allowed,
};

function renderShell(
  initial: LayoutPreferencesValue = DEFAULT_LAYOUT,
  cityInstances: CityInstanceGateway = emptyCityInstances,
  datasets: CityDataset[] = [],
  runs: RunGateway = fakeRunGateway(),
) {
  const saved: LayoutPreferencesValue[] = [];
  const gateways: Gateways = {
    systemStatus: { load: () => Promise.resolve(status) },
    layoutPreferences: {
      load: () => initial,
      save: (value) => {
        saved.push(value);
      },
    },
    cityDatasets: { list: () => Promise.resolve(datasets) },
    basemap: { exists: () => Promise.resolve(false), url: () => '' },
    cityInstances,
    runs,
  };
  const { factory, maps } = fakeMapFactory();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  // The empty-Lab tests start from a menu already known to be empty (story 2-10, 2026-11-27).
  if (cityInstances === emptyCityInstances) client.setQueryData(INSTANCE_MENU_KEY, []);
  render(
    <QueryClientProvider client={client}>
      <GatewaysProvider gateways={gateways}>
        <MapFactoryProvider factory={factory}>
          <LabShell />
        </MapFactoryProvider>
      </GatewaysProvider>
    </QueryClientProvider>,
  );
  return { saved, maps };
}

const grip = () => screen.getByRole('separator');

let stubs: ReturnType<typeof installBrowserStubs>;

beforeEach(() => {
  window.location.hash = '#/lab';
  stubs = installBrowserStubs(false);
});

afterEach(() => {
  stubs.restore();
  window.location.hash = '';
  document.documentElement.style.removeProperty('font-size');
});

describe('LabShell · the empty Lab', () => {
  it('shows the menu, the top bar, the card, the map pane and the footer', () => {
    const { maps } = renderShell();

    expect(screen.getByText('Dynamic pricing · Lab')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Hide the menu' })).toBeInTheDocument();
    expect(screen.getByText('Operator view')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'City instances' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(screen.getByText('No instance yet')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Compare versions' })).toBeInTheDocument();
    expect(screen.getByText('Traveller view')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Trip options and prices' })).toBeInTheDocument();
    expect(screen.getByRole('switch', { name: 'Advanced view' })).toHaveAttribute(
      'aria-checked',
      'false',
    );
    expect(screen.getByText('No run in progress')).toBeInTheDocument();
    expect(screen.getByLabelText('Breadcrumb')).toHaveTextContent('City instances');
    expect(screen.getByRole('button', { name: 'Hide map' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Larger text for a projector' })).toBeInTheDocument();
    expect(
      screen.getByText(
        'No city instance yet. Create one from the Geneva data: it prepares the area, the hubs, the routes and the travellers of one period.',
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Map' })).toContainElement(
      maps[0]?.container ?? null,
    );
    expect(maps).toHaveLength(1);
    expect(
      screen.getByText('Funded by the European Union under Horizon Europe, project SUM.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('contentinfo')).toHaveTextContent(
      'Pricing model: placeholder, Inria INOCS.',
    );
  });

  it('has none of the elements the story leaves out', () => {
    renderShell();

    for (const text of ['← Home', 'Next version', 'Simulation', 'Run unmodified']) {
      expect(screen.queryByText(text, { exact: false })).not.toBeInTheDocument();
    }
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });

  it('opens the off state of Compare versions and of the traveller view', async () => {
    renderShell();
    const user = userEvent.setup();

    await user.click(screen.getByRole('button', { name: 'Compare versions' }));
    expect(
      screen.getByText('Compare needs two pricing versions of this city instance.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Compare versions' })).toHaveAttribute(
      'aria-current',
      'page',
    );

    await user.click(screen.getByRole('button', { name: 'Trip options and prices' }));
    expect(screen.getByText('Run a pricing version first.')).toBeInTheDocument();
  });

  it('hides and brings back the menu', async () => {
    const { saved } = renderShell();
    const user = userEvent.setup();

    await user.click(screen.getByRole('button', { name: 'Hide the menu' }));
    expect(screen.queryByText('Dynamic pricing · Lab')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '☰ Menu' }));

    expect(screen.getByText('Dynamic pricing · Lab')).toBeInTheDocument();
    expect(saved.map((value) => value.menuOpen)).toEqual([false, true]);
  });

  it('hides and shows the map without creating another', async () => {
    const { maps } = renderShell();
    const user = userEvent.setup();

    await user.click(screen.getByRole('button', { name: 'Hide map' }));
    expect(screen.queryByRole('region', { name: 'Map' })).not.toBeInTheDocument();
    expect(screen.queryByRole('separator')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Show map' }));
    expect(screen.getByRole('region', { name: 'Map' })).toBeInTheDocument();
    expect(maps).toHaveLength(1);
    expect(maps[0]?.removed).toBe(false);
  });

  it('turns the projector type scale on and off', async () => {
    const { saved } = renderShell();
    const user = userEvent.setup();
    const aa = screen.getByRole('button', { name: 'Larger text for a projector' });

    await user.click(aa);
    expect(document.documentElement.style.fontSize).toBe('130%');
    await user.click(aa);
    expect(document.documentElement.style.fontSize).toBe('');
    expect(saved.map((value) => value.largeText)).toEqual([true, false]);
  });

  it('keeps the Advanced view choice', async () => {
    const { saved } = renderShell();

    await userEvent.setup().click(screen.getByRole('switch', { name: 'Advanced view' }));

    expect(screen.getByRole('switch', { name: 'Advanced view' })).toHaveAttribute(
      'aria-checked',
      'true',
    );
    expect(saved.at(-1)?.advancedView).toBe(true);
  });

  it('starts from the preferences it loads', () => {
    renderShell({
      ...DEFAULT_LAYOUT,
      menuOpen: false,
      mapShown: false,
      largeText: true,
      mapShare: { instance: 36 },
    });

    expect(screen.queryByText('Dynamic pricing · Lab')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Show map' })).toBeInTheDocument();
    expect(document.documentElement.style.fontSize).toBe('130%');
  });
});

describe('LabShell · the grip', () => {
  it('is a focusable vertical separator with its label and the 50 % default', () => {
    renderShell();

    expect(grip()).toHaveAttribute('aria-orientation', 'vertical');
    expect(grip()).toHaveAttribute('tabindex', '0');
    expect(grip()).toHaveAccessibleName('Drag to make the map wider or narrower');
    expect(grip()).toHaveAttribute('aria-valuenow', '50');
  });

  it('moves by 2 points per arrow key, ← widening the map', async () => {
    const { saved } = renderShell();
    const user = userEvent.setup();
    grip().focus();

    await user.keyboard('{ArrowLeft}{ArrowLeft}');
    expect(grip()).toHaveAttribute('aria-valuenow', '54');
    await user.keyboard('{ArrowRight}');
    expect(grip()).toHaveAttribute('aria-valuenow', '52');
    expect(saved.at(-1)?.mapShare).toEqual({ instance: 52 });
  });

  it('clamps so that neither card nor map is under 20 %', async () => {
    renderShell({ ...DEFAULT_LAYOUT, mapShare: { instance: 79 } });
    const user = userEvent.setup();
    grip().focus();

    await user.keyboard('{ArrowLeft}{ArrowLeft}');
    expect(grip()).toHaveAttribute('aria-valuenow', '80');

    for (let press = 0; press < 40; press += 1) await user.keyboard('{ArrowRight}');
    expect(grip()).toHaveAttribute('aria-valuenow', '20');
  });

  it('ignores other keys', async () => {
    renderShell();
    grip().focus();

    await userEvent.setup().keyboard('{ArrowUp}');

    expect(grip()).toHaveAttribute('aria-valuenow', '50');
  });
});

describe('LabShell · keyboard in the menu', () => {
  it('moves between the four items with ↑ and ↓ and opens one with Enter', async () => {
    renderShell();
    const user = userEvent.setup();
    screen.getByRole('button', { name: 'City instances' }).focus();

    await user.keyboard('{ArrowDown}');
    expect(screen.getByRole('button', { name: '+ New' })).toHaveFocus();
    await user.keyboard('{ArrowDown}');
    expect(screen.getByRole('button', { name: 'Compare versions' })).toHaveFocus();
    await user.keyboard('{ArrowDown}');
    expect(screen.getByRole('button', { name: 'Trip options and prices' })).toHaveFocus();
    await user.keyboard('{ArrowDown}');
    expect(screen.getByRole('button', { name: 'City instances' })).toHaveFocus();
    await user.keyboard('{ArrowUp}{ArrowUp}{Enter}');

    expect(screen.getByRole('button', { name: 'Compare versions' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(
      screen.getByText('Compare needs two pricing versions of this city instance.'),
    ).toBeInTheDocument();
  });

  it('leaves other keys alone', async () => {
    renderShell();
    screen.getByRole('button', { name: 'City instances' }).focus();

    await userEvent.setup().keyboard('a');

    expect(screen.getByRole('button', { name: 'City instances' })).toHaveFocus();
  });
});

describe('LabShell · the route', () => {
  it('reads "Nothing at this link" for a link naming an instance version', () => {
    window.location.hash = '#/lab/geneva-3km.v1';
    renderShell();

    expect(
      screen.getByText('Nothing at this link: geneva-3km has no v1. It may have been deleted.'),
    ).toBeInTheDocument();
    expect(screen.getByLabelText('Breadcrumb')).toHaveTextContent('City instances');
  });

  it('keeps the menu usable on an unknown link', async () => {
    window.location.hash = '#/lab/geneva-3km.v1/result/B';
    renderShell();

    await userEvent.setup().click(screen.getByRole('button', { name: 'Compare versions' }));

    expect(
      screen.getByText('Compare needs two pricing versions of this city instance.'),
    ).toBeInTheDocument();
    expect(window.location.hash).toBe('#/lab');
  });

  it('replaces a hash that does not parse by #/lab without a history entry', () => {
    const before = window.history.length;
    window.location.hash = '#/play';
    const afterHashChange = window.history.length;
    renderShell();

    expect(window.location.hash).toBe('#/lab');
    expect(window.history.length).toBe(afterHashChange);
    expect(afterHashChange).toBeGreaterThanOrEqual(before);
    expect(screen.getByText(/^No city instance yet\./)).toBeInTheDocument();
  });

  it('follows a hash change', async () => {
    renderShell();

    window.location.hash = '#/lab/geneva-3km.v2';
    await vi.waitFor(() => {
      expect(
        screen.getByText('Nothing at this link: geneva-3km has no v2. It may have been deleted.'),
      ).toBeInTheDocument();
    });
  });
});

describe('LabShell · an open instance version', () => {
  const instances = (overrides: Partial<CityInstanceGateway> = {}) => fakeCityInstances(overrides);

  it('lists the instances: the open one expanded with its set-up and pricing versions, the others with a count', async () => {
    window.location.hash = '#/lab/geneva-3km.v1';
    renderShell(DEFAULT_LAYOUT, instances());

    const setup = await screen.findByRole('button', { name: 'Instance set-up' });

    expect(setup).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('button', { name: 'City instances' })).not.toHaveAttribute(
      'aria-current',
    );
    expect(screen.getByRole('button', { name: '+ New' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Geneva 3 km v1 ready' })).toBeInTheDocument();
    expect(screen.getByText('Pricing versions')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Geneva 2 km v1 1 version' })).toBeInTheDocument();
    expect(screen.queryByText('No instance yet')).not.toBeInTheDocument();
  });

  it('writes the breadcrumb and the period chip once the version is read', async () => {
    window.location.hash = '#/lab/geneva-3km.v1';
    renderShell(DEFAULT_LAYOUT, instances());

    expect(await screen.findByText('Period Monday 08:00–09:00')).toBeInTheDocument();
    expect(screen.getByLabelText('Breadcrumb')).toHaveTextContent(
      'Geneva 3 km v1 › Instance set-up',
    );
  });

  it('shows the skeleton while the version is read, then the saved card', async () => {
    window.location.hash = '#/lab/geneva-3km.v1';
    let release: () => void = () => undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    renderShell(
      DEFAULT_LAYOUT,
      instances({
        version: async (id) => {
          await gate;
          return id === sampleVersion.id ? sampleVersion : null;
        },
      }),
    );

    // The menu answers first (its skeleton gives way to the version read's skeleton).
    await screen.findByRole('button', { name: 'Instance set-up' });
    expect(screen.getByRole('status', { name: 'Loading' })).toBeInTheDocument();
    release();

    expect(await screen.findByText('City instance · pipeline steps 1 to 4')).toBeInTheDocument();
    expect(screen.queryByRole('status', { name: 'Loading' })).not.toBeInTheDocument();
  });

  it('shows the skeleton, not "Nothing at this link", while the menu is read', async () => {
    window.location.hash = '#/lab/geneva-3km.v1';
    let release: () => void = () => undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const base = instances();
    renderShell(
      DEFAULT_LAYOUT,
      instances({
        menu: async () => {
          await gate;
          return base.menu();
        },
      }),
    );

    expect(await screen.findByRole('status', { name: 'Loading' })).toBeInTheDocument();
    expect(screen.queryByText(/Nothing at this link/)).not.toBeInTheDocument();
    expect(screen.getByLabelText('Breadcrumb')).toHaveTextContent('City instances');
    release();

    expect(await screen.findByText('City instance · pipeline steps 1 to 4')).toBeInTheDocument();
    expect(screen.queryByText(/Nothing at this link/)).not.toBeInTheDocument();
  });

  it('shows the read error, not "Nothing at this link", when the menu cannot be read', async () => {
    window.location.hash = '#/lab/geneva-3km.v1';
    renderShell(DEFAULT_LAYOUT, instances({ menu: () => Promise.reject(new Error('offline')) }));

    expect(
      await screen.findByText(/The city instance could not be read: offline/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Nothing at this link/)).not.toBeInTheDocument();
    expect(screen.queryByText(/may have been deleted/)).not.toBeInTheDocument();
  });

  it('writes "No instance yet" only once the menu has answered with no instance', async () => {
    let release: () => void = () => undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    renderShell(
      DEFAULT_LAYOUT,
      instances({
        menu: async () => {
          await gate;
          return [];
        },
      }),
    );

    expect(screen.queryByText('No instance yet')).not.toBeInTheDocument();
    release();

    expect(await screen.findByText('No instance yet')).toBeInTheDocument();
  });

  it('has no period chip when no instance version is open', () => {
    renderShell();

    expect(screen.queryByText(/^Period /)).not.toBeInTheDocument();
  });

  it('names the instance on a link to a version it does not have', async () => {
    window.location.hash = '#/lab/geneva-3km.v7';
    renderShell(DEFAULT_LAYOUT, instances());

    expect(
      await screen.findByText(
        'Nothing at this link: Geneva 3 km has no v7. It may have been deleted.',
      ),
    ).toBeInTheDocument();
    expect(screen.getByLabelText('Breadcrumb')).toHaveTextContent('City instances');
  });

  it('opens an instance version from its menu row', async () => {
    renderShell(DEFAULT_LAYOUT, instances());
    const user = userEvent.setup();

    await user.click(await screen.findByRole('button', { name: 'Geneva 3 km v1 1 version' }));

    expect(window.location.hash).toBe('#/lab/geneva-3km.v1');
    expect(await screen.findByText('City instance · pipeline steps 1 to 4')).toBeInTheDocument();
  });

  it('keeps arrow-key movement across the instance rows', async () => {
    window.location.hash = '#/lab/geneva-3km.v1';
    renderShell(DEFAULT_LAYOUT, instances());
    const setup = await screen.findByRole('button', { name: 'Instance set-up' });
    setup.focus();

    const user = userEvent.setup();

    // The instance's "Delete…" follows its first version row in the menu's keyboard order.
    await user.keyboard('{ArrowUp}');
    expect(
      within(screen.getByRole('complementary', { name: 'Menu' })).getByRole('button', {
        name: 'Delete…',
      }),
    ).toHaveFocus();
    await user.keyboard('{ArrowUp}');
    expect(screen.getByRole('button', { name: 'Geneva 3 km v1 ready' })).toHaveFocus();
  });
});

describe('LabShell · creating and editing', () => {
  const dataset: CityDataset = {
    id: 'geneva-2026-11-26',
    centre: { lat: 46.2, lon: 6.14 },
    radiusM: 3000,
    availableArea: [6, 46, 6.3, 46.4],
  };

  it('puts "+ New" in the empty Lab menu and "+ New city instance" on the card', async () => {
    renderShell(DEFAULT_LAYOUT, emptyCityInstances, [dataset]);

    expect(screen.getByRole('button', { name: 'City instances' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '+ New' })).toBeInTheDocument();
    expect(screen.getByText('No instance yet')).toBeInTheDocument();
    expect(
      screen.getByText(
        'No city instance yet. Create one from the Geneva data: it prepares the area, the hubs, the routes and the travellers of one period.',
      ),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole('button', { name: '+ New city instance' })).toBeEnabled();
    });
    expect(screen.queryByText(/No city data is imported yet/)).not.toBeInTheDocument();
  });

  it('disables the primary and says why while no city data is imported', async () => {
    renderShell(DEFAULT_LAYOUT, emptyCityInstances, []);

    expect(
      await screen.findByText(
        "No city data is imported yet. A city instance needs a timetable and bike stations; the maintainer imports Geneva's with one command (demo/README.md).",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '+ New city instance' })).toBeDisabled();
  });

  it.each(['+ New', '+ New city instance'])(
    'opens the new-instance form from "%s"',
    async (label) => {
      renderShell(DEFAULT_LAYOUT, emptyCityInstances, [dataset]);
      const user = userEvent.setup();
      await waitFor(() => {
        expect(screen.getByRole('button', { name: '+ New city instance' })).toBeEnabled();
      });

      await user.click(screen.getByRole('button', { name: label }));

      expect(await screen.findByRole('heading', { name: 'New city instance' })).toBeInTheDocument();
      expect(screen.getByRole('textbox', { name: 'Name' })).toHaveValue('');
      expect(screen.queryByRole('button', { name: '+ New city instance' })).not.toBeInTheDocument();
    },
  );

  it('opens the new-instance form from "+ New" while a saved version is open', async () => {
    window.location.hash = '#/lab/geneva-3km.v1';
    renderShell(DEFAULT_LAYOUT, fakeCityInstances(), [dataset]);
    const user = userEvent.setup();
    await screen.findByRole('button', { name: 'Edit as a new version' });

    await user.click(screen.getByRole('button', { name: '+ New' }));

    expect(await screen.findByRole('heading', { name: 'New city instance' })).toBeInTheDocument();
    expect(window.location.hash).toBe('#/lab');
  });

  it('closes the new-instance form with any other link', async () => {
    renderShell(DEFAULT_LAYOUT, emptyCityInstances, [dataset]);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: '+ New' }));
    await screen.findByRole('heading', { name: 'New city instance' });

    await user.click(screen.getByRole('button', { name: 'Compare versions' }));

    expect(screen.queryByRole('heading', { name: 'New city instance' })).not.toBeInTheDocument();
    expect(
      screen.getByText('Compare needs two pricing versions of this city instance.'),
    ).toBeInTheDocument();
  });

  it('creates the instance on Name blur and opens its draft as the new-instance form', async () => {
    const state = { created: false };
    const draftOne = {
      ...sampleDraft,
      id: 'geneva-4km.v1',
      instanceId: 'geneva-4km',
      number: 1,
      basedOnId: null,
    };
    const cityInstances = fakeCityInstances({
      menu: () =>
        Promise.resolve(
          state.created
            ? [
                {
                  id: 'geneva-4km',
                  name: 'Geneva 4 km',
                  datasetId: 'geneva-2026-11-26',
                  versions: [
                    {
                      id: 'geneva-4km.v1',
                      number: 1,
                      status: 'draft',
                      state: 'draft',
                      pricingVersionCount: 0,
                    },
                  ],
                },
              ]
            : [],
        ),
      createInstance: () => {
        state.created = true;
        return Promise.resolve({ kind: 'created', version: draftOne });
      },
      version: (id) => Promise.resolve(id === 'geneva-4km.v1' ? draftOne : null),
    });
    renderShell(DEFAULT_LAYOUT, cityInstances, [dataset]);
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: '+ New' }));

    await user.type(await screen.findByRole('textbox', { name: 'Name' }), 'Geneva 4 km{Enter}');

    expect(
      await screen.findByRole('heading', { name: 'Geneva 4 km · new version (draft)' }),
    ).toBeInTheDocument();
    expect(window.location.hash).toBe('#/lab/geneva-4km.v1');
    expect(screen.getByRole('textbox', { name: 'Name' })).toHaveAttribute('readonly');
    expect(screen.getByRole('button', { name: 'Save as v1 and build' })).toBeInTheDocument();
  });

  const firstEntry = sampleMenu[0] ?? { id: '', name: '', datasetId: '', versions: [] };

  function menuWithDraft(drafted: { value: boolean }) {
    return () =>
      Promise.resolve(
        drafted.value
          ? [
              {
                ...firstEntry,
                versions: [
                  ...(sampleMenu[0]?.versions ?? []),
                  {
                    id: 'geneva-3km.v2',
                    number: 2,
                    status: 'draft' as const,
                    state: 'draft',
                    pricingVersionCount: 0,
                  },
                ],
              },
              ...sampleMenu.slice(1),
            ]
          : sampleMenu,
      );
  }

  it('"Edit as a new version" creates the draft and opens its form', async () => {
    window.location.hash = '#/lab/geneva-3km.v1';
    const drafted = { value: false };
    const createDraft = vi.fn(() => {
      drafted.value = true;
      return Promise.resolve({ kind: 'created' as const, version: sampleDraft });
    });
    renderShell(DEFAULT_LAYOUT, fakeCityInstances({ menu: menuWithDraft(drafted), createDraft }));
    const user = userEvent.setup();

    await user.click(await screen.findByRole('button', { name: 'Edit as a new version' }));

    expect(createDraft).toHaveBeenCalledWith('geneva-3km', 'geneva-3km.v1');
    expect(
      await screen.findByRole('heading', { name: 'Geneva 3 km · new version (draft)' }),
    ).toBeInTheDocument();
    expect(window.location.hash).toBe('#/lab/geneva-3km.v2');
    expect(screen.queryByText(/already has a draft/)).not.toBeInTheDocument();
  });

  it('opens the draft the instance already has, with the one-draft sentence', async () => {
    window.location.hash = '#/lab/geneva-3km.v1';
    const drafted = { value: true };
    renderShell(
      DEFAULT_LAYOUT,
      fakeCityInstances({
        menu: menuWithDraft(drafted),
        createDraft: () => Promise.resolve({ kind: 'draft_exists', draftId: 'geneva-3km.v2' }),
      }),
    );
    const user = userEvent.setup();

    await user.click(await screen.findByRole('button', { name: 'Edit as a new version' }));

    expect(
      await screen.findByText(
        'This instance already has a draft, started from v1 on 24 Nov. Continue it, or discard it first.',
      ),
    ).toBeInTheDocument();
    expect(window.location.hash).toBe('#/lab/geneva-3km.v2');
  });

  it('shows the draft form for a link to a draft version', async () => {
    window.location.hash = '#/lab/geneva-3km.v2';
    renderShell(DEFAULT_LAYOUT, fakeCityInstances({ menu: menuWithDraft({ value: true }) }));

    expect(
      await screen.findByRole('heading', { name: 'Geneva 3 km · new version (draft)' }),
    ).toBeInTheDocument();
    expect(screen.queryByText('Instance set-up', { selector: 'h2' })).not.toBeInTheDocument();
    expect(screen.getByLabelText('Breadcrumb')).toHaveTextContent(
      'Geneva 3 km v2 › Instance set-up',
    );
  });
});

describe('LabShell · run states in the menu', () => {
  const states = ['building', 'queued', 'failed', 'cancelled', 'ready'] as const;
  const menuWith = () =>
    Promise.resolve([
      {
        id: 'geneva-3km',
        name: 'Geneva 3 km',
        datasetId: 'geneva-2026-11-26',
        versions: states.map((state, at) => ({
          id: `geneva-3km.v${String(at + 1)}`,
          number: at + 1,
          status: 'sealed' as const,
          state,
          pricingVersionCount: 0,
        })),
      },
    ]);

  it('writes each version row with its run state and the place of a queued build', async () => {
    window.location.hash = '#/lab/geneva-3km.v5';
    const running = {
      ...sampleRunningBuild,
      subject: { type: 'instance_version' as const, id: 'geneva-3km.v1' },
    };
    const queued = {
      ...sampleRunningBuild,
      id: 'run-3',
      state: 'queued' as const,
      queuePosition: 1,
      subject: { type: 'instance_version' as const, id: 'geneva-3km.v2' },
      steps: sampleBuildSteps(5),
    };
    renderShell(
      DEFAULT_LAYOUT,
      fakeCityInstances({
        menu: menuWith,
        version: (id) => Promise.resolve(id === 'geneva-3km.v5' ? sampleVersion : null),
      }),
      [],
      fakeRunGateway([running, queued]),
    );

    expect(await screen.findByRole('button', { name: 'Geneva 3 km v1 ● building' })).toBeVisible();
    await screen.findByRole('button', { name: 'Geneva 3 km v2 ◷ queued · 2nd' });
    expect(screen.getByRole('button', { name: 'Geneva 3 km v3 ✕ failed' })).toBeVisible();
    expect(screen.getByRole('button', { name: 'Geneva 3 km v4 cancelled' })).toBeVisible();
    expect(screen.getByRole('button', { name: 'Geneva 3 km v5 ready' })).toBeVisible();
    expect(screen.queryByText('Available when the instance is built.')).not.toBeInTheDocument();
  });

  it('turns "Pricing versions" off until the open instance is built', async () => {
    window.location.hash = '#/lab/geneva-3km.v1';
    renderShell(
      DEFAULT_LAYOUT,
      fakeCityInstances({
        menu: menuWith,
        version: () =>
          Promise.resolve({ ...sampleVersion, id: 'geneva-3km.v1', state: 'building' }),
      }),
    );

    expect(await screen.findByText('Available when the instance is built.')).toBeVisible();
    expect(screen.getByText('Pricing versions')).toBeVisible();
  });

  it('writes the run in progress on the run line of the menu', async () => {
    const running = {
      ...sampleRunningBuild,
      startedAt: new Date(Date.now() - 252_000),
      serverTime: new Date(),
      subject: { type: 'instance_version' as const, id: 'geneva-3km.v1' },
    };
    renderShell(
      DEFAULT_LAYOUT,
      fakeCityInstances({ menu: menuWith }),
      [],
      fakeRunGateway([running]),
    );

    expect(await screen.findByText(/^● Geneva 3 km v1 building · 4 min 1\d s$/)).toBeVisible();
  });

  it('still says a build is ready when it ended while the menu was hidden', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      const running = {
        ...sampleRunningBuild,
        startedAt: new Date(Date.now() - 252_000),
        serverTime: new Date(),
        subject: { type: 'instance_version' as const, id: 'geneva-3km.v1' },
      };
      const runs = fakeRunGateway([running]);
      renderShell(DEFAULT_LAYOUT, fakeCityInstances({ menu: menuWith }), [], runs);
      await screen.findByText(/^● Geneva 3 km v1 building/);

      await user.click(screen.getByRole('button', { name: 'Hide the menu' }));
      runs.put({ ...running, state: 'succeeded', steps: sampleBuildSteps(5) });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(2000);
      });
      await waitFor(() => {
        expect(runs.calls).toContain(`get ${running.id}`);
      });
      await user.click(screen.getByRole('button', { name: '☰ Menu' }));

      expect(await screen.findByText(/^✓ Geneva 3 km v1: ready ·/)).toBeVisible();
    } finally {
      vi.useRealTimers();
    }
  });
});

describe('LabShell · deleting an instance from its menu row', () => {
  const states = ['ready', 'failed'] as const;
  const twoVersions = () =>
    Promise.resolve([
      {
        id: 'geneva-3km',
        name: 'Geneva 3 km',
        datasetId: 'geneva-2026-11-26',
        versions: states.map((state, at) => ({
          id: `geneva-3km.v${String(at + 1)}`,
          number: at + 1,
          status: 'sealed' as const,
          state,
          pricingVersionCount: 0,
        })),
      },
    ]);
  const menuNav = () => screen.findByRole('navigation', { name: '' });

  beforeEach(() => {
    window.location.hash = '#/lab/geneva-3km.v1';
  });

  it('asks what goes, naming the versions, and "Keep" closes it', async () => {
    renderShell(DEFAULT_LAYOUT, fakeCityInstances({ menu: twoVersions }));
    const user = userEvent.setup();

    await user.click(await within(await menuNav()).findByRole('button', { name: 'Delete…' }));

    expect(
      screen.getByText(
        'Delete Geneva 3 km? This removes its 2 versions (v1, v2). This cannot be undone.',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Delete Geneva 3 km and its versions' }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Keep' }));
    expect(screen.queryByText(/This removes its/)).not.toBeInTheDocument();
  });

  it('writes the singular for one version', async () => {
    renderShell(DEFAULT_LAYOUT, fakeCityInstances());
    const user = userEvent.setup();

    await user.click(await within(await menuNav()).findByRole('button', { name: 'Delete…' }));

    expect(
      screen.getByText(
        'Delete Geneva 3 km? This removes its 1 version (v1). This cannot be undone.',
      ),
    ).toBeInTheDocument();
  });

  it('deletes the instance and opens #/lab', async () => {
    const deleteInstance = vi.fn(() => Promise.resolve({ kind: 'deleted' as const }));
    renderShell(DEFAULT_LAYOUT, fakeCityInstances({ menu: twoVersions, deleteInstance }));
    const user = userEvent.setup();

    await user.click(await within(await menuNav()).findByRole('button', { name: 'Delete…' }));
    await user.click(screen.getByRole('button', { name: 'Delete Geneva 3 km and its versions' }));

    await waitFor(() => {
      expect(window.location.hash).toBe('#/lab');
    });
    expect(deleteInstance).toHaveBeenCalledWith('geneva-3km');
  });

  it('shows the refusal as the note of the menu row\'s "Delete…" and deletes nothing', async () => {
    renderShell(DEFAULT_LAYOUT, fakeCityInstances({ menu: twoVersions }, new Set(['geneva-3km'])));
    const user = userEvent.setup();

    await user.click(await within(await menuNav()).findByRole('button', { name: 'Delete…' }));
    await user.click(screen.getByRole('button', { name: 'Delete Geneva 3 km and its versions' }));

    expect(
      await within(await menuNav()).findByText('A run of this version is queued or running.'),
    ).toBeVisible();
    expect(window.location.hash).toBe('#/lab/geneva-3km.v1');
  });
});
