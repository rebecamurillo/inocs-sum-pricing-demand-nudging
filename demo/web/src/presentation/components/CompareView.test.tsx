import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { fakeCityInstances, sampleMenu } from '../../application/ports/fake-city-instance-gateway';
import {
  fakePricing,
  samplePricingDraft,
  sampleSealedPricing,
} from '../../application/ports/fake-pricing-gateway';
import { fakeRunGateway } from '../../application/ports/fake-run-gateway';
import type { Gateways } from '../../application/ports/gateways';
import type { LabRoute } from '../../domain/route';
import type { SystemStatus, Verdict } from '../../domain/system-status';
import { GatewaysProvider } from '../hooks/gateways';
import { CompareView } from './CompareView';

const finished = (letter: string, goals: Parameters<typeof sampleSealedPricing>[0] = {}) =>
  sampleSealedPricing({
    id: `geneva-3km.v1.${letter}`,
    letter,
    name: `Version ${letter}`,
    ...goals,
  });

const allowed: Verdict = { allowed: true, reasons: [] };
const status: SystemStatus = {
  components: [],
  canBuildInstances: allowed,
  canRunPricing: allowed,
  canSimulate: allowed,
  simulationRule: { id: 'balanced-score', version: 2 },
};

function mount(
  options: {
    versions?: ReturnType<typeof sampleSealedPricing>[];
    letters?: readonly string[] | null;
    details?: Parameters<typeof fakePricing>[2];
    advancedView?: boolean;
  } = {},
) {
  const fake = fakePricing(
    options.versions ?? [finished('A'), finished('B'), finished('C')],
    {},
    options.details,
  );
  const onNavigate = vi.fn<(route: LabRoute) => void>();
  const onReplace = vi.fn<(route: LabRoute) => void>();
  const onAdvancedView = vi.fn<(on: boolean) => void>();
  const gateways: Gateways = {
    systemStatus: { load: () => Promise.resolve(status) },
    layoutPreferences: { load: vi.fn(), save: vi.fn() },
    cityDatasets: { list: () => Promise.resolve([]) },
    basemap: { exists: () => Promise.resolve(false), url: () => '' },
    cityInstances: fakeCityInstances({ menu: () => Promise.resolve(sampleMenu) }),
    runs: fakeRunGateway(),
    pricing: fake.gateway,
  };
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = (letters: readonly string[] | null) => (
    <QueryClientProvider client={client}>
      <GatewaysProvider gateways={gateways}>
        <CompareView
          instanceVersionId="geneva-3km.v1"
          instanceId="geneva-3km"
          number={1}
          letters={letters}
          period={null}
          advancedView={options.advancedView ?? false}
          onAdvancedView={onAdvancedView}
          onNavigate={onNavigate}
          onReplace={onReplace}
        />
      </GatewaysProvider>
    </QueryClientProvider>
  );
  const { rerender } = render(
    view(options.letters === undefined ? ['A', 'B', 'C'] : options.letters),
  );
  return {
    fake,
    onNavigate,
    onReplace,
    onAdvancedView,
    rerender: (letters: readonly string[] | null) => {
      rerender(view(letters));
    },
  };
}

const table = async () => within(await screen.findByTestId('compare-table'));
const cellsOf = (id: string) => within(screen.getByTestId(id)).getAllByRole('cell');
const present = (element: HTMLElement | undefined): HTMLElement => {
  if (element === undefined) throw new Error('No such cell.');
  return element;
};

describe('CompareView', () => {
  it('shows the brief, the picker, the flat pill and the scope without a screen-wide tag', async () => {
    mount();

    expect(await screen.findByText('Versions of one city instance, side by side')).toBeVisible();
    const picker = screen.getByRole('list', { name: 'Versions to compare' });
    const pills = within(picker).getAllByRole('button');
    expect(pills.map((pill) => pill.textContent)).toEqual([
      '✓ A · Version A',
      '✓ B · Version B',
      '✓ C · Version C',
    ]);
    expect(pills.every((pill) => pill.getAttribute('aria-pressed') === 'true')).toBe(true);
    expect(
      within(picker).getByText('Flat price 1.00 CHF · simulated · always shown'),
    ).toBeVisible();
    expect(screen.getByText('Geneva 3 km v1 · Monday 08:00–09:00')).toBeVisible();
    expect(screen.getByRole('switch', { name: 'Advanced view' })).toBeVisible();
    // Only the bars' source block and the table's group carry a SIMULATION tag.
    const insight = screen.getByRole('heading', { level: 2 });
    expect(insight.textContent).toMatch(/^In the simulation, /);
  });

  it('draws one bar per column, flat first, with three legend keys and the three-mode sentence', async () => {
    mount();
    const bars = within(
      await screen.findByRole('list', { name: 'Simulated split of the travellers' }),
    );

    expect(
      bars.getAllByRole('img').map((bar) => bar.getAttribute('aria-label')?.split(':')[0]),
    ).toEqual([
      'Flat price 1.00 CHF',
      'Version A · Version A',
      'Version B · Version B',
      'Version C · Version C',
    ]);
    expect(
      within(screen.getByRole('list', { name: 'Modes' })).getAllByRole('listitem'),
    ).toHaveLength(3);
    expect(
      screen.getByText(
        /The pricing model prices a shared bike only together with a public transport trip/,
      ),
    ).toBeVisible();
  });

  it('builds the table: columns, groups, tags, dashes in flat columns, no "Shared bike" row', async () => {
    mount();
    const grid = await table();

    expect(
      grid
        .getAllByRole('columnheader')
        .map((header) => header.textContent)
        .slice(1),
    ).toEqual([
      'Flat price 1.00 CHF',
      'Version A · Version A',
      'Version B · Version B',
      'Version C · Version C',
    ]);
    expect(
      grid
        .getAllByRole('rowheader')
        .filter((h) => h.getAttribute('scope') === 'rowgroup')
        .map((h) => h.textContent),
    ).toEqual([
      expect.stringMatching(/^SIMULATIONSimulated travellers/),
      expect.stringMatching(/^PRICING MODEL'S RESULTPricing model's result/),
      "Computed from the model's flows",
    ]);
    expect(grid.queryByText('Shared bike')).toBeNull();
    const cells = cellsOf('row-simulated-share_car');
    expect(cells.map((cell) => cell.textContent)).toEqual([
      '55 %',
      '50 %−5 pts',
      '42 %−13 pts',
      '34 %−21 pts',
    ]);
  });

  it('marks the best value of a row with a green ground and the flat column shows its own value', async () => {
    mount();
    await table();
    const [flat, a, b, c] = cellsOf('row-simulated-share_car');

    expect(flat?.textContent).toBe('55 %');
    expect(a?.getAttribute('data-best')).toBeNull();
    expect(b?.getAttribute('data-best')).toBeNull();
    expect(c?.getAttribute('data-best')).toBe('');
    expect(c?.textContent).toBe('34 %−21 pts');
    expect(cellsOf('row-model-bike_price_range')[0]?.textContent).toBe('—');
  });

  it('shows the solver rows with the Advanced view on and none with it off', async () => {
    mount({ advancedView: true });
    expect(await screen.findByText('= Objective value')).toBeVisible();
    expect(screen.getByText('Hub pairs · bike options offered')).toBeVisible();
    expect(screen.getAllByText('optimal')).toHaveLength(3);
  });

  it('has no solver rows with the Advanced view off', async () => {
    mount();
    await screen.findByTestId('compare-table');
    expect(screen.queryByText('= Objective value')).toBeNull();
  });

  it('switches the Advanced view from the card', async () => {
    const { onAdvancedView } = mount();
    await userEvent.click(await screen.findByRole('switch', { name: 'Advanced view' }));
    expect(onAdvancedView).toHaveBeenCalledWith(true);
  });

  it('lists only the goals that differ, the differing value in bold, the flat price included', async () => {
    mount({
      versions: [
        finished('A'),
        finished('B'),
        finished('C', { goals: { flat_price_per_ride_chf: 1.5 } }),
      ],
    });
    const grid = await table();

    const cells = cellsOf('row-goals_that_differ-flat_price_per_ride_chf');
    expect(cells.map((cell) => cell.textContent)).toEqual([
      '—',
      '1.00 CHF',
      '1.00 CHF',
      '—',
      '1.50 CHF',
    ]);
    expect(within(present(cells[4])).getByText('1.50 CHF').className).toMatch(/bold/);
    expect(within(present(cells[2])).getByText('1.00 CHF').className).not.toMatch(/bold/);
    expect(grid.queryByText('Cost of one ride')).toBeNull();
    expect(
      grid
        .getAllByRole('columnheader')
        .map((h) => h.textContent)
        .filter((t) => t.startsWith('Flat')),
    ).toEqual(['Flat price 1.00 CHF · for A, B', 'Flat price 1.50 CHF · for C']);
  });

  it('closes with the caption and the same-basis note', async () => {
    mount();
    expect(
      await screen.findByText(
        'Small figures: change against the flat-price column the version is simulated with. The pricing model is not run with a flat price: its rows show — there.',
      ),
    ).toBeVisible();
    expect(screen.getByText('same hubs, routes, travellers and bikes.')).toBeVisible();
  });

  describe('notices', () => {
    it('says nothing when every version has one build', async () => {
      mount();
      await screen.findByTestId('compare-table');
      expect(screen.queryByText(/different builds/)).toBeNull();
    });

    it('names two package commits', async () => {
      mount({ details: { comparison: { commits: { 'geneva-3km.v1.B': 'bbbbbbb1111' } } } });
      expect(
        await screen.findByText(
          "These versions were run with different builds of the pricing model (package commits aaaaaaa and bbbbbbb): a difference can come from the model's code, not only from the goals.",
        ),
      ).toBeVisible();
    });

    it('names three package commits', async () => {
      mount({
        details: {
          comparison: {
            commits: { 'geneva-3km.v1.B': 'bbbbbbb1111', 'geneva-3km.v1.C': 'ccccccc2222' },
          },
        },
      });
      expect(
        await screen.findByText(/package commits aaaaaaa, bbbbbbb and ccccccc\)/),
      ).toBeVisible();
    });

    it('greys an older rule, offers "Simulate B again" and calls simulate for that version', async () => {
      const { fake } = mount({ details: { comparison: { olderRule: { 'geneva-3km.v1.B': 1 } } } });

      expect(
        await screen.findByText(
          'Version B was simulated with an older rule (v1): its simulated numbers are greyed. Simulate it again to compare like with like.',
        ),
      ).toBeVisible();
      const grid = await table();
      const headers = grid.getAllByRole('columnheader');
      // The flat column of the older rule is separate and greyed; so is the version's.
      expect(headers.filter((h) => h.hasAttribute('data-stale')).map((h) => h.textContent)).toEqual(
        ['Flat price 1.00 CHF · for B', 'Version B · Version B'],
      );
      expect(
        screen.getByText(
          /Simulated travellers · placeholder rule: half price, half travel time · older rule \(v1\)/,
          { selector: 'p' },
        ),
      ).toBeVisible();

      await userEvent.click(screen.getByRole('button', { name: 'Simulate B again' }));

      await waitFor(() => {
        expect(fake.simulated()).toEqual(['geneva-3km.v1.B']);
      });
    });
  });

  describe('the picker', () => {
    it('rewrites the route in place when a version is unticked, and ticks it again', async () => {
      const { onReplace, rerender } = mount();
      await userEvent.click(await screen.findByRole('button', { name: '✓ B · Version B' }));
      expect(onReplace).toHaveBeenLastCalledWith({
        kind: 'compare',
        instance: { instanceId: 'geneva-3km', version: 1 },
        letters: ['A', 'C'],
        period: null,
      });

      rerender(['A', 'C']);
      expect(await screen.findByRole('button', { name: 'B · Version B' })).toHaveAttribute(
        'aria-pressed',
        'false',
      );
      expect(screen.queryByRole('columnheader', { name: /Version B/ })).toBeNull();
      await userEvent.click(screen.getByRole('button', { name: 'B · Version B' }));
      expect(onReplace).toHaveBeenLastCalledWith(
        expect.objectContaining({ letters: ['A', 'B', 'C'] }),
      );
    });

    it('disables the ticked pills while two are ticked and the unticked ones while four are', async () => {
      const versions = ['A', 'B', 'C', 'D', 'E'].map((letter) => finished(letter));
      const two = mount({ versions, letters: ['A', 'B'] });
      expect(await screen.findByRole('button', { name: '✓ A · Version A' })).toBeDisabled();
      expect(screen.getByRole('button', { name: '✓ B · Version B' })).toBeDisabled();
      expect(screen.getByRole('button', { name: 'C · Version C' })).toBeEnabled();

      two.rerender(['A', 'B', 'C', 'D']);
      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'E · Version E' })).toBeDisabled();
      });
      expect(screen.getByRole('button', { name: '✓ D · Version D' })).toBeEnabled();
    });

    it('writes the one spelling of a route whose letters are out of order', async () => {
      const { onReplace } = mount({ letters: ['C', 'A'] });
      await waitFor(() => {
        expect(onReplace).toHaveBeenCalledWith({
          kind: 'compare',
          instance: { instanceId: 'geneva-3km', version: 1 },
          letters: ['A', 'C'],
          period: null,
        });
      });
    });
  });

  describe('the off state and the unknown letter', () => {
    it('offers "+ New pricing version" with fewer than two finished versions', async () => {
      const { onNavigate } = mount({
        versions: [finished('A'), samplePricingDraft({ id: 'geneva-3km.v1.B', letter: 'B' })],
        letters: null,
      });

      expect(await screen.findByText('Versions of one city instance, side by side')).toBeVisible();
      expect(
        screen.getByText('Compare needs two pricing versions of this city instance.'),
      ).toBeVisible();
      await userEvent.click(screen.getByRole('button', { name: '+ New pricing version' }));

      await waitFor(() => {
        expect(onNavigate).toHaveBeenCalledWith(
          expect.objectContaining({ kind: 'pricing', letter: 'C' }),
        );
      });
    });

    it('opens with the finished versions ticked when it has no letters', async () => {
      const { onNavigate } = mount({ letters: null });
      await waitFor(() => {
        expect(onNavigate).toHaveBeenCalledWith(
          expect.objectContaining({ kind: 'compare', letters: ['A', 'B', 'C'] }),
        );
      });
    });

    it('says there is nothing at the link for a letter that is not a finished version', async () => {
      mount({ letters: ['A', 'Z'] });
      expect(
        await screen.findByText(
          'Nothing at this link: Geneva 3 km v1 has no Version Z. It may have been deleted.',
        ),
      ).toBeVisible();
    });
  });
});
