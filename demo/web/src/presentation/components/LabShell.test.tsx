import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Gateways } from '../../application/ports/gateways';
import { DEFAULT_LAYOUT, type LayoutPreferencesValue } from '../../domain/layout';
import type { SystemStatus } from '../../domain/system-status';
import { GatewaysProvider } from '../hooks/gateways';
import { LabShell } from './LabShell';

const allowed = { allowed: true, reasons: [] };
const status: SystemStatus = {
  components: [],
  canBuildInstances: allowed,
  canRunPricing: allowed,
  canSimulate: allowed,
};

function renderShell(initial: LayoutPreferencesValue = DEFAULT_LAYOUT) {
  const saved: LayoutPreferencesValue[] = [];
  const gateways: Gateways = {
    systemStatus: { load: () => Promise.resolve(status) },
    layoutPreferences: {
      load: () => initial,
      save: (value) => {
        saved.push(value);
      },
    },
  };
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <GatewaysProvider gateways={gateways}>
        <LabShell />
      </GatewaysProvider>
    </QueryClientProvider>,
  );
  return { saved };
}

const grip = () => screen.getByRole('separator');

beforeEach(() => {
  window.location.hash = '#/lab';
});

afterEach(() => {
  window.location.hash = '';
  document.documentElement.style.removeProperty('font-size');
});

describe('LabShell · the empty Lab', () => {
  it('shows the menu, the top bar, the card, the map pane and the footer', () => {
    renderShell();

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
    expect(screen.getByRole('region', { name: 'Map' })).toBeEmptyDOMElement();
    expect(
      screen.getByText('Funded by the European Union under Horizon Europe, project SUM.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('contentinfo')).toHaveTextContent(
      'Pricing model: placeholder, Inria INOCS.',
    );
  });

  it('has none of the elements the story leaves out', () => {
    renderShell();

    for (const text of ['← Home', 'Next version', 'Simulation', '+ New', 'Run unmodified']) {
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

  it('hides and shows the map', async () => {
    renderShell();
    const user = userEvent.setup();

    await user.click(screen.getByRole('button', { name: 'Hide map' }));
    expect(screen.queryByRole('region', { name: 'Map' })).not.toBeInTheDocument();
    expect(screen.queryByRole('separator')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Show map' }));
    expect(screen.getByRole('region', { name: 'Map' })).toBeInTheDocument();
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
  it('moves between the three items with ↑ and ↓ and opens one with Enter', async () => {
    renderShell();
    const user = userEvent.setup();
    screen.getByRole('button', { name: 'City instances' }).focus();

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
