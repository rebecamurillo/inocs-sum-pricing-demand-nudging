import { emptyTrips } from '../../application/ports/fake-trip-gateway';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, render, screen, waitFor, within } from '@testing-library/react';
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
import {
  fakePricing,
  fakePricingGateway,
  samplePricingDraft,
  samplePricingResult,
  sampleSealedPricing,
} from '../../application/ports/fake-pricing-gateway';
import type { PricingGateway } from '../../application/ports/pricing-gateway';
import type { Gateways } from '../../application/ports/gateways';
import {
  fakeRunGateway,
  sampleBuildSteps,
  sampleRunningBuild,
  sampleStep,
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
  simulationRule: null,
};

function renderShell(
  initial: LayoutPreferencesValue = DEFAULT_LAYOUT,
  cityInstances: CityInstanceGateway = emptyCityInstances,
  datasets: CityDataset[] = [],
  runs: RunGateway = fakeRunGateway(),
  pricing: PricingGateway = fakePricingGateway(),
  systemStatus: SystemStatus = status,
) {
  const saved: LayoutPreferencesValue[] = [];
  const gateways: Gateways = {
    systemStatus: { load: () => Promise.resolve(systemStatus) },
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
    pricing,
    trips: emptyTrips,
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
                      pricingVersionLetters: [],
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
                    pricingVersionLetters: [],
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
          pricingVersionLetters: [],
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
          pricingVersionLetters: [],
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
    const oneVersion = () =>
      Promise.resolve([
        {
          id: 'geneva-3km',
          name: 'Geneva 3 km',
          datasetId: 'geneva-2026-11-26',
          versions: [
            {
              id: 'geneva-3km.v1',
              number: 1,
              status: 'sealed' as const,
              state: 'ready',
              pricingVersionCount: 0,
              pricingVersionLetters: [],
            },
          ],
        },
      ]);
    renderShell(DEFAULT_LAYOUT, fakeCityInstances({ menu: oneVersion }));
    const user = userEvent.setup();

    await user.click(await within(await menuNav()).findByRole('button', { name: 'Delete…' }));

    expect(
      screen.getByText(
        'Delete Geneva 3 km? This removes its 1 version (v1). This cannot be undone.',
      ),
    ).toBeInTheDocument();
  });

  it('names the pricing versions that go with the instance and sends the flag', async () => {
    const deleteInstance = vi.fn(() => Promise.resolve({ kind: 'deleted' as const }));
    renderShell(DEFAULT_LAYOUT, fakeCityInstances({ deleteInstance }));
    const user = userEvent.setup();

    await user.click(await within(await menuNav()).findByRole('button', { name: 'Delete…' }));

    expect(
      screen.getByText(
        'Delete Geneva 3 km? This removes its 1 version (v1) and their 3 pricing versions with their results. This cannot be undone.',
      ),
    ).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Delete Geneva 3 km and its versions' }));
    await waitFor(() => {
      expect(window.location.hash).toBe('#/lab');
    });
    expect(deleteInstance).toHaveBeenCalledWith('geneva-3km', true);
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
    expect(deleteInstance).toHaveBeenCalledWith('geneva-3km', false);
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

describe('LabShell · pricing versions', () => {
  const versions = () => [
    sampleSealedPricing({ id: 'geneva-3km.v1.A', letter: 'A', name: 'Version A', state: 'result' }),
    sampleSealedPricing({
      id: 'geneva-3km.v1.B',
      letter: 'B',
      name: 'Balance first',
      state: 'queued',
    }),
    sampleSealedPricing({
      id: 'geneva-3km.v1.C',
      letter: 'C',
      name: 'Lower floor',
      state: 'failed',
    }),
    samplePricingDraft({ id: 'geneva-3km.v1.D', letter: 'D', name: 'Version D' }),
  ];
  const queuedBuild = {
    ...sampleRunningBuild,
    id: 'run-pricing-B',
    state: 'queued' as const,
    queuePosition: 1,
    subject: { type: 'pricing_version' as const, id: 'geneva-3km.v1.B' },
  };

  function open(hash: string, layout: LayoutPreferencesValue = DEFAULT_LAYOUT) {
    window.location.hash = hash;
    return renderShell(
      layout,
      fakeCityInstances(),
      [],
      fakeRunGateway([queuedBuild]),
      fakePricingGateway(versions()),
    );
  }

  it('lists the pricing versions under the open instance version with their states', async () => {
    open('#/lab/geneva-3km.v1');

    expect(await screen.findByRole('button', { name: 'Version A ✓ result' })).toBeVisible();
    expect(screen.getByRole('button', { name: /^Balance first B ◷ queued · 2nd$/ })).toBeVisible();
    expect(screen.getByRole('button', { name: /^Lower floor C ✕ failed$/ })).toBeVisible();
    expect(screen.getByRole('button', { name: 'New version draft' })).toBeVisible();
    expect(screen.getAllByRole('button', { name: '+ New pricing version' })).toHaveLength(2);
    const menu = screen.getByRole('complementary', { name: 'Menu' });
    expect(within(menu).getByRole('button', { name: '+ New pricing version' })).toBeVisible();
  });

  it('shows a version with a result as simulating while a simulation run of it is queued or running', async () => {
    const simulation = {
      ...queuedBuild,
      id: 'run-sim-A',
      kind: 'simulation' as const,
      state: 'running' as const,
      queuePosition: null,
      subject: { type: 'pricing_version' as const, id: 'geneva-3km.v1.A' },
    };
    window.location.hash = '#/lab/geneva-3km.v1';
    renderShell(
      DEFAULT_LAYOUT,
      fakeCityInstances(),
      [],
      fakeRunGateway([queuedBuild, simulation]),
      fakePricingGateway(versions()),
    );

    expect(await screen.findByRole('button', { name: 'Version A ● simulating' })).toBeVisible();
    expect(screen.getByRole('button', { name: /^Balance first B ◷ queued · 2nd$/ })).toBeVisible();
  });

  it('reads the result again when the simulation run ends: the box goes and the row is a result again', async () => {
    const older = samplePricingResult();
    const outcome = (version: number, current: boolean) => ({
      ...older.simulations.flat,
      ruleVersion: version,
      ruleCurrent: current,
    });
    const stale = {
      ...older,
      simulations: { modelPrices: outcome(1, false), flat: outcome(1, false) },
    };
    let fresh = false;
    const stored = fakePricing(versions());
    const pricing: PricingGateway = {
      ...stored.gateway,
      result: (id) => (fresh ? stored.gateway.result(id) : Promise.resolve(stale)),
    };
    const simulation = {
      ...queuedBuild,
      id: 'run-sim-A',
      kind: 'simulation' as const,
      state: 'running' as const,
      queuePosition: null,
      subject: { type: 'pricing_version' as const, id: 'geneva-3km.v1.A' },
    };
    const runs = fakeRunGateway([simulation]);
    window.location.hash = '#/lab/geneva-3km.v1/result/A';
    renderShell(DEFAULT_LAYOUT, fakeCityInstances(), [], runs, pricing, {
      ...status,
      simulationRule: { id: 'balanced-score', version: 2 },
    });
    const box = await screen.findByTestId('older-rule');
    expect(await within(box).findByText(/^Traveller simulation · running for/)).toBeVisible();

    fresh = true;
    runs.put({ ...simulation, state: 'succeeded' });

    await waitFor(
      () => {
        expect(screen.queryByTestId('older-rule')).toBeNull();
      },
      { timeout: 6000 },
    );
    expect(screen.getByRole('button', { name: 'Version A ✓ result' })).toBeVisible();
  }, 10000);

  it('opens a draft or a queued version at its L-2 route and a result at its result route', async () => {
    open('#/lab/geneva-3km.v1');
    const user = userEvent.setup();

    await user.click(await screen.findByRole('button', { name: 'New version draft' }));
    expect(window.location.hash).toBe('#/lab/geneva-3km.v1/pricing/D');

    await user.click(screen.getByRole('button', { name: /^Balance first B/ }));
    expect(window.location.hash).toBe('#/lab/geneva-3km.v1/pricing/B');

    await user.click(screen.getByRole('button', { name: 'Version A ✓ result' }));
    expect(window.location.hash).toBe('#/lab/geneva-3km.v1/result/A');
    expect(screen.getByRole('button', { name: 'Version A ✓ result' })).toHaveAttribute(
      'aria-current',
      'page',
    );
  });

  it('starts a draft from "+ New pricing version" and opens its route', async () => {
    open('#/lab/geneva-3km.v1');

    const menu = await screen.findByRole('complementary', { name: 'Menu' });
    await userEvent.click(
      await within(menu).findByRole('button', { name: '+ New pricing version' }),
    );

    await waitFor(() => {
      expect(window.location.hash).toBe('#/lab/geneva-3km.v1/pricing/E');
    });
    expect(await screen.findByRole('heading', { name: 'Pricing goals' })).toBeVisible();
  });

  it('shows the pricing goals card at the L-2 route, with the breadcrumb and no map', async () => {
    open('#/lab/geneva-3km.v1/pricing/D');

    expect(await screen.findByRole('heading', { name: 'Pricing goals' })).toBeVisible();
    expect(screen.getByLabelText('Breadcrumb')).toHaveTextContent(
      'Geneva 3 km v1 › Pricing versions › New version',
    );
    expect(screen.getByRole('button', { name: 'New version draft' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(screen.getByRole('button', { name: 'Instance set-up' })).not.toHaveAttribute(
      'aria-current',
    );
    expect(screen.queryByRole('separator')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Hide map' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Show map' })).not.toBeInTheDocument();
  });

  it('brings the map back on L-1 without having changed the stored choice', async () => {
    const { saved } = open('#/lab/geneva-3km.v1/pricing/D');
    await screen.findByRole('heading', { name: 'Pricing goals' });

    await userEvent.click(screen.getByRole('button', { name: 'Instance set-up' }));

    expect(await screen.findByRole('separator')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Hide map' })).toBeInTheDocument();
    expect(saved).toEqual([]);
  });

  it('keeps the map hidden on L-1 when the stored choice is hidden', async () => {
    open('#/lab/geneva-3km.v1/pricing/D', { ...DEFAULT_LAYOUT, mapShown: false });
    await screen.findByRole('heading', { name: 'Pricing goals' });

    await userEvent.click(screen.getByRole('button', { name: 'Instance set-up' }));

    expect(await screen.findByRole('button', { name: 'Show map' })).toBeInTheDocument();
  });

  it('says nothing is there for an unknown letter', async () => {
    open('#/lab/geneva-3km.v1/pricing/Q');

    expect(
      await screen.findByText(
        'Nothing at this link: Geneva 3 km v1 has no Version Q. It may have been deleted.',
      ),
    ).toBeVisible();
  });

  it('shows the run card at the L-2 route of a queued, a failed and a cancelled version, not the goals form', async () => {
    const withRuns = [
      sampleSealedPricing({
        id: 'geneva-3km.v1.B',
        letter: 'B',
        name: 'Balance first',
        state: 'queued',
        runId: 'run-pricing-B',
      }),
      sampleSealedPricing({
        id: 'geneva-3km.v1.C',
        letter: 'C',
        name: 'Lower floor',
        state: 'failed',
        runId: 'run-pricing-C',
      }),
      sampleSealedPricing({
        id: 'geneva-3km.v1.E',
        letter: 'E',
        name: 'Cheaper',
        state: 'cancelled',
        runId: 'run-pricing-E',
      }),
    ];
    const run = (letter: string, state: 'failed' | 'cancelled') => ({
      ...sampleRunningBuild,
      id: `run-pricing-${letter}`,
      kind: 'pricing' as const,
      state,
      finishedAt: new Date('2026-11-27T10:00:00Z'),
      subject: { type: 'pricing_version' as const, id: `geneva-3km.v1.${letter}` },
      steps: [
        sampleStep({
          step: 'pricing_model',
          number: 5,
          state: state === 'failed' ? 'failed' : 'cancelled',
        }),
        sampleStep({ step: 'traveller_simulation', number: 6 }),
      ],
      failure:
        state === 'failed'
          ? { step: 'pricing_model', code: 'solver_size_limited', reason: 'x' }
          : null,
    });
    const gateway = fakeRunGateway([queuedBuild, run('C', 'failed'), run('E', 'cancelled')]);
    const render = (hash: string) => {
      window.location.hash = hash;
      return renderShell(
        DEFAULT_LAYOUT,
        fakeCityInstances(),
        [],
        gateway,
        fakePricingGateway(withRuns),
      );
    };

    render('#/lab/geneva-3km.v1/pricing/B');
    expect(await screen.findByText(/^5 Pricing model — waiting/)).toBeVisible();
    expect(screen.getByRole('button', { name: 'Running…' })).toBeDisabled();
    expect(screen.queryByRole('heading', { name: 'Pricing goals' })).not.toBeInTheDocument();
    cleanup();

    render('#/lab/geneva-3km.v1/pricing/C');
    expect(
      await screen.findByText(
        "Pricing model failed: Gurobi's size-limited licence cannot solve this instance. Steps before it are kept.",
      ),
    ).toBeVisible();
    expect(screen.getByRole('button', { name: 'Run again from Pricing model' })).toBeVisible();
    cleanup();

    render('#/lab/geneva-3km.v1/pricing/E');
    expect(
      await screen.findByText(/^Run cancelled during Pricing model on 27 Nov 2026\./),
    ).toBeVisible();
    expect(screen.getByRole('button', { name: 'Duplicate' })).toBeVisible();
  });

  it('opens the result card on the result route of a finished version', async () => {
    open('#/lab/geneva-3km.v1/result/A');

    expect(await screen.findByLabelText('Breadcrumb')).toHaveTextContent(
      'Geneva 3 km v1 › Pricing versions › Version A',
    );
    expect(await screen.findByText('Result · pipeline step 6')).toBeVisible();
    expect(screen.queryByRole('heading', { name: 'Pricing goals' })).not.toBeInTheDocument();
    expect(screen.queryByText(/Nothing at this link/)).not.toBeInTheDocument();
  });

  it('shows the map on L-3 of a finished version, at 36 % under its own key, with Hide map', async () => {
    const { saved } = open('#/lab/geneva-3km.v1/result/A');
    await screen.findByText('Result · pipeline step 6');

    expect(screen.getByRole('button', { name: 'Hide map' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Map' })).toBeInTheDocument();
    expect(grip()).toHaveAttribute('aria-valuenow', '36');

    grip().focus();
    await userEvent.keyboard('{ArrowLeft}');
    expect(grip()).toHaveAttribute('aria-valuenow', '38');
    expect(saved.at(-1)?.mapShare).toEqual({ instance: 50, result: 38 });
  });

  it('gives the card the full width on L-3 with Hide map, and keeps the share of L-1 apart', async () => {
    open('#/lab/geneva-3km.v1/result/A', {
      ...DEFAULT_LAYOUT,
      mapShare: { instance: 60, result: 30 },
    });
    await screen.findByText('Result · pipeline step 6');
    expect(grip()).toHaveAttribute('aria-valuenow', '30');

    await userEvent.click(screen.getByRole('button', { name: 'Hide map' }));
    expect(screen.queryByRole('separator')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Show map' })).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Show map' }));
    await userEvent.click(screen.getByRole('button', { name: 'Instance set-up' }));
    expect(await screen.findByRole('separator')).toHaveAttribute('aria-valuenow', '60');
  });

  it('has no map on the result route of a version that is not finished', async () => {
    open('#/lab/geneva-3km.v1/result/D');
    await screen.findByRole('heading', { name: 'Pricing goals' });

    expect(screen.queryByRole('separator')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Hide map' })).not.toBeInTheDocument();
  });

  it('shows the run card on the result route of a cancelled version and the goals form of a draft', async () => {
    const cancelled = sampleSealedPricing({
      id: 'geneva-3km.v1.E',
      letter: 'E',
      name: 'Cheaper',
      state: 'cancelled',
      runId: 'run-pricing-E',
    });
    const run = {
      ...sampleRunningBuild,
      id: 'run-pricing-E',
      kind: 'pricing' as const,
      state: 'cancelled' as const,
      finishedAt: new Date('2026-11-27T10:00:00Z'),
      subject: { type: 'pricing_version' as const, id: 'geneva-3km.v1.E' },
      steps: [
        sampleStep({ step: 'pricing_model', number: 5, state: 'cancelled' }),
        sampleStep({ step: 'traveller_simulation', number: 6 }),
      ],
      failure: null,
    };
    window.location.hash = '#/lab/geneva-3km.v1/result/E';
    renderShell(
      DEFAULT_LAYOUT,
      fakeCityInstances(),
      [],
      fakeRunGateway([run]),
      fakePricingGateway([cancelled, ...versions()]),
    );
    expect(
      await screen.findByText(/^Run cancelled during Pricing model on 27 Nov 2026\./),
    ).toBeVisible();
    expect(screen.queryByText('Result · pipeline step 6')).not.toBeInTheDocument();
    cleanup();

    open('#/lab/geneva-3km.v1/result/D');
    expect(await screen.findByRole('heading', { name: 'Pricing goals' })).toBeVisible();
    expect(screen.queryByText('Result · pipeline step 6')).not.toBeInTheDocument();
  });

  it('reads "Available when the instance is built." at the L-2 route of a version that is not built', async () => {
    window.location.hash = '#/lab/geneva-3km.v1/pricing/A';
    renderShell(
      DEFAULT_LAYOUT,
      fakeCityInstances({
        menu: () =>
          Promise.resolve([
            {
              id: 'geneva-3km',
              name: 'Geneva 3 km',
              datasetId: 'geneva-2026-11-26',
              versions: [
                {
                  id: 'geneva-3km.v1',
                  number: 1,
                  status: 'sealed' as const,
                  state: 'building' as const,
                  pricingVersionCount: 0,
                  pricingVersionLetters: [],
                },
              ],
            },
          ]),
      }),
    );

    expect(await screen.findAllByText('Available when the instance is built.')).toHaveLength(2);
    expect(screen.queryByRole('heading', { name: 'Pricing goals' })).not.toBeInTheDocument();
  });

  it('shows the banner on L-2 when pricing runs are off', async () => {
    window.location.hash = '#/lab/geneva-3km.v1/pricing/D';
    renderShell(
      DEFAULT_LAYOUT,
      fakeCityInstances(),
      [],
      fakeRunGateway(),
      fakePricingGateway(versions()),
      {
        ...status,
        components: [{ name: 'solver', state: 'limited', reason: 'size-limited' }],
        canRunPricing: {
          allowed: false,
          reasons: [{ component: 'solver', reason: 'size-limited' }],
        },
      },
    );

    expect(
      await screen.findAllByText(
        /Pricing runs are off: this machine has Gurobi's size-limited licence/,
      ),
    ).toHaveLength(2);
    expect(
      screen.getByRole('button', { name: 'Run the pricing model · 08:00–09:00' }),
    ).toBeDisabled();
  });
});

describe('LabShell · compare versions (L-4)', () => {
  const finished = (letter: string) =>
    sampleSealedPricing({ id: `geneva-3km.v1.${letter}`, letter, name: `Version ${letter}` });

  function open(hash: string, versions = ['A', 'B', 'C'].map(finished), layout = DEFAULT_LAYOUT) {
    window.location.hash = hash;
    return renderShell(
      layout,
      fakeCityInstances(),
      [],
      fakeRunGateway(),
      fakePricingGateway(versions),
    );
  }

  it('shows L-4 on its route with its breadcrumb, the period chip, 34 % for the map and the menu item current', async () => {
    open('#/lab/geneva-3km.v1/compare/A,B');

    expect(await screen.findByText('Versions of one city instance, side by side')).toBeVisible();
    expect(screen.getByLabelText('Breadcrumb')).toHaveTextContent(
      'Geneva 3 km v1 › Compare versions',
    );
    expect(screen.getByRole('button', { name: 'Compare versions' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(grip()).toHaveAttribute('aria-valuenow', '34');
    expect(
      screen.getByRole('list', { name: 'Versions to compare' }).querySelectorAll('button'),
    ).toHaveLength(3);
  });

  it('replaces the hash in place when a version is unticked, and keeps the history length', async () => {
    open('#/lab/geneva-3km.v1/compare/A,B,C');
    const user = userEvent.setup();
    const before = window.history.length;

    await user.click(await screen.findByRole('button', { name: '✓ B · Version B' }));

    await waitFor(() => {
      expect(window.location.hash).toBe('#/lab/geneva-3km.v1/compare/A,C');
    });
    expect(window.history.length).toBe(before);
    expect(await screen.findByRole('button', { name: 'B · Version B' })).toHaveAttribute(
      'aria-pressed',
      'false',
    );
    await waitFor(() => {
      expect(screen.queryByRole('columnheader', { name: /Version B/ })).not.toBeInTheDocument();
    });
  });

  it('writes the one spelling of letters out of order', async () => {
    open('#/lab/geneva-3km.v1/compare/C,A');
    await screen.findByText('Versions of one city instance, side by side');
    await waitFor(() => {
      expect(window.location.hash).toBe('#/lab/geneva-3km.v1/compare/A,C');
    });
  });

  it('opens from the menu item with an instance version open, with every finished version ticked', async () => {
    open('#/lab/geneva-3km.v1');
    const user = userEvent.setup();
    await screen.findByRole('button', { name: 'Edit as a new version' });

    await user.click(screen.getByRole('button', { name: 'Compare versions' }));

    await waitFor(() => {
      expect(window.location.hash).toBe('#/lab/geneva-3km.v1/compare/A,B,C');
    });
    expect(await screen.findByRole('button', { name: '✓ A · Version A' })).toBeVisible();
  });

  it('shows the off state in place when the instance version has fewer than two finished versions', async () => {
    open('#/lab/geneva-3km.v1', [finished('A')]);
    const user = userEvent.setup();
    await screen.findByRole('button', { name: 'Edit as a new version' });

    await user.click(screen.getByRole('button', { name: 'Compare versions' }));

    expect(
      await screen.findByText('Compare needs two pricing versions of this city instance.'),
    ).toBeVisible();
    expect(
      within(screen.getByRole('main')).getByRole('button', { name: '+ New pricing version' }),
    ).toBeVisible();
    expect(window.location.hash).toBe('#/lab/geneva-3km.v1');
  });

  it('opens from the primary of L-3, and shows the off state when only one version is finished', async () => {
    open('#/lab/geneva-3km.v1/result/B');
    const user = userEvent.setup();

    await user.click(await screen.findByRole('button', { name: 'Compare versions →' }));

    await waitFor(() => {
      expect(window.location.hash).toBe('#/lab/geneva-3km.v1/compare/A,B,C');
    });
    cleanup();

    open('#/lab/geneva-3km.v1/result/A', [finished('A')]);
    await user.click(await screen.findByRole('button', { name: 'Compare versions →' }));
    expect(
      await screen.findByText('Compare needs two pricing versions of this city instance.'),
    ).toBeVisible();
  });

  it('says there is nothing at the link for an unknown letter and for an unknown instance version', async () => {
    open('#/lab/geneva-3km.v1/compare/A,Z');
    expect(
      await screen.findByText(
        'Nothing at this link: Geneva 3 km v1 has no Version Z. It may have been deleted.',
      ),
    ).toBeVisible();
    cleanup();

    open('#/lab/geneva-3km.v9/compare/A,B');
    expect(await screen.findByText(/Nothing at this link: .* has no v9\./)).toBeVisible();
  });
});

describe('LabShell · trip options and prices (L-5)', () => {
  const version = (letter: string, state: 'result' | 'draft' | 'failed') =>
    state === 'result'
      ? sampleSealedPricing({ id: `geneva-3km.v1.${letter}`, letter, name: `Version ${letter}` })
      : samplePricingDraft({
          id: `geneva-3km.v1.${letter}`,
          letter,
          name: `Version ${letter}`,
          state,
          status: state === 'draft' ? 'draft' : 'sealed',
        });

  function open(
    hash: string,
    versions = [version('A', 'result'), version('B', 'draft'), version('C', 'result')],
  ) {
    window.location.hash = hash;
    return renderShell(
      DEFAULT_LAYOUT,
      fakeCityInstances(),
      [],
      fakeRunGateway(),
      fakePricingGateway(versions),
    );
  }

  it('opens the first finished version from the menu item and shows L-5 with its share', async () => {
    open('#/lab');
    const user = userEvent.setup();

    await user.click(await screen.findByRole('button', { name: 'Trip options and prices' }));

    await waitFor(() => {
      expect(window.location.hash).toBe('#/lab/traveller/geneva-3km.v1/A');
    });
    expect(await screen.findByRole('combobox', { name: 'Pricing version' })).toHaveValue(
      'geneva-3km.v1.A',
    );
    expect(screen.getByRole('button', { name: 'Trip options and prices' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(screen.getByLabelText('Breadcrumb')).toHaveTextContent('Trip options and prices');
    expect(grip()).toHaveAttribute('aria-valuenow', '44');
  });

  it('waits for the finished versions when the menu item is clicked before they are read', async () => {
    let release: () => void = () => undefined;
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    const pricing = fakePricingGateway([version('A', 'result')]);
    const list = pricing.list.bind(pricing);
    pricing.list = async (instanceVersionId) => {
      await held;
      return list(instanceVersionId);
    };
    window.location.hash = '#/lab';
    renderShell(DEFAULT_LAYOUT, fakeCityInstances(), [], fakeRunGateway(), pricing);
    const user = userEvent.setup();

    await user.click(await screen.findByRole('button', { name: 'Trip options and prices' }));
    expect(screen.queryByText('Run a pricing version first.')).toBeNull();
    release();

    await waitFor(() => {
      expect(window.location.hash).toBe('#/lab/traveller/geneva-3km.v1/A');
    });
  });

  it('opens the version of the current link when it is finished', async () => {
    open('#/lab/geneva-3km.v1/result/C');
    const user = userEvent.setup();

    await user.click(await screen.findByRole('button', { name: 'Trip options and prices' }));

    await waitFor(() => {
      expect(window.location.hash).toBe('#/lab/traveller/geneva-3km.v1/C');
    });
  });

  it('replaces a link to a version that is not finished by the first finished version', async () => {
    open('#/lab/traveller/geneva-3km.v1/B');

    expect(await screen.findByRole('combobox', { name: 'Pricing version' })).toHaveValue(
      'geneva-3km.v1.A',
    );
    expect(window.location.hash).toBe('#/lab/traveller/geneva-3km.v1/A');
  });

  it('chooses the version the link names after a reload', async () => {
    open('#/lab/traveller/geneva-3km.v1/C?period=mon-08');

    expect(await screen.findByRole('combobox', { name: 'Pricing version' })).toHaveValue(
      'geneva-3km.v1.C',
    );
  });

  it('says there is nothing at the link for an unknown letter and for an unknown instance version', async () => {
    open('#/lab/traveller/geneva-3km.v1/Z');
    expect(
      await screen.findByText(
        'Nothing at this link: Geneva 3 km v1 has no Version Z. It may have been deleted.',
      ),
    ).toBeVisible();
    cleanup();

    open('#/lab/traveller/geneva-3km.v9/A');
    expect(await screen.findByText(/Nothing at this link: .* has no v9\./)).toBeVisible();
  });

  it('reads "Run a pricing version first." when no version is finished', async () => {
    open('#/lab', [version('B', 'draft'), version('C', 'failed')]);
    const user = userEvent.setup();

    await user.click(await screen.findByRole('button', { name: 'Trip options and prices' }));

    expect(await screen.findByText('Run a pricing version first.')).toBeVisible();
    expect(screen.queryByRole('combobox', { name: 'Pricing version' })).not.toBeInTheDocument();

    cleanup();
    open('#/lab/traveller/geneva-3km.v1/B', [version('B', 'draft')]);
    expect(await screen.findByText('Run a pricing version first.')).toBeVisible();
  });
});
