import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fakeCityInstances, sampleMenu } from '../../application/ports/fake-city-instance-gateway';
import {
  fakePricing,
  samplePairDifference,
  samplePricingDraft,
  sampleSealedPricing,
} from '../../application/ports/fake-pricing-gateway';
import { fakeRunGateway } from '../../application/ports/fake-run-gateway';
import type { Gateways } from '../../application/ports/gateways';
import type { LabRoute } from '../../domain/route';
import type { SystemStatus, Verdict } from '../../domain/system-status';
import { GatewaysProvider } from '../hooks/gateways';
import { fakeMapFactory, installBrowserStubs } from '../map/fake-map';
import { MapFactoryProvider, MapProvider } from '../map/MapContext';
import { MapPane } from '../map/MapPane';
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

let stubs: ReturnType<typeof installBrowserStubs>;
beforeEach(() => {
  stubs = installBrowserStubs(false);
});
afterEach(() => {
  // Unmount first: the map's last effects still read `matchMedia`.
  cleanup();
  stubs.restore();
});

function mount(
  options: {
    versions?: ReturnType<typeof sampleSealedPricing>[];
    letters?: readonly string[] | null;
    details?: Parameters<typeof fakePricing>[2];
    advancedView?: boolean;
    hubs?: { id: string; label: string; lat: number; lon: number }[];
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
    cityInstances: fakeCityInstances({
      menu: () => Promise.resolve(sampleMenu),
      ...(options.hubs === undefined
        ? {}
        : {
            hubs: () =>
              Promise.resolve(options.hubs?.map((hub) => ({ ...hub, outline: null })) ?? []),
          }),
    }),
    runs: fakeRunGateway(),
    pricing: fake.gateway,
  };
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const { factory, maps } = fakeMapFactory();
  const view = (letters: readonly string[] | null) => (
    <QueryClientProvider client={client}>
      <GatewaysProvider gateways={gateways}>
        <MapFactoryProvider factory={factory}>
          <MapProvider>
            <MapPane shown datasetId={null} />
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
          </MapProvider>
        </MapFactoryProvider>
      </GatewaysProvider>
    </QueryClientProvider>
  );
  const { rerender } = render(
    view(options.letters === undefined ? ['A', 'B', 'C'] : options.letters),
  );
  const map = maps[0];
  if (map !== undefined) {
    act(() => {
      map.emitStyleReady();
    });
  }
  return {
    fake,
    map,
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

  describe('the CSV export', () => {
    it('saves the file of the loaded comparison and asks the API for nothing more', async () => {
      const created = vi.fn<(blob: Blob) => string>(() => 'blob:csv');
      vi.stubGlobal('URL', { createObjectURL: created, revokeObjectURL: vi.fn() });
      const names: string[] = [];
      const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
        this: HTMLAnchorElement,
      ) {
        names.push(this.download);
      });
      try {
        const { fake } = mount();
        const compare = vi.spyOn(fake.gateway, 'compare');
        const button = await screen.findByRole('button', { name: 'Export the table (CSV)' });
        expect(button).toBeEnabled();
        expect(button.previousElementSibling?.textContent).toBe(
          'same hubs, routes, travellers and bikes.',
        );
        const before = compare.mock.calls.length;
        await userEvent.click(button);
        expect(click).toHaveBeenCalledTimes(1);
        expect(names).toEqual(['comparison-geneva-3km.v1-ABC.csv']);
        const blob = created.mock.calls[0]?.[0];
        expect(blob?.type).toBe('text/csv;charset=utf-8');
        expect((await blob?.text())?.startsWith('version,')).toBe(true);
        expect(compare).toHaveBeenCalledTimes(before);
      } finally {
        click.mockRestore();
        vi.unstubAllGlobals();
      }
    });

    it('is absent in the off state', async () => {
      mount({ versions: [finished('A')], letters: null });
      await screen.findByText('Compare needs two pricing versions of this city instance.');
      expect(screen.queryByRole('button', { name: 'Export the table (CSV)' })).toBeNull();
    });
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

  describe('where prices differ', () => {
    const twelve = Array.from({ length: 12 }, (_, at) =>
      samplePairDifference(
        `H${String(at + 1)}`,
        'H20',
        1,
        at === 1 ? 0.7 : at === 2 ? 1 : 1.25 + at / 100,
        3000,
        4500,
      ),
    );
    const hubs = [...twelve.map((pair) => pair.originHub), 'H20'].map((id, at) => ({
      id,
      label: id === 'H1' ? 'H1 Plainpalais' : id,
      lat: 46.2 + at / 1000,
      lon: 6.14,
    }));
    const sampleHubs = ['H4', 'H9', 'H12'].map((id, at) => ({
      id,
      label: id,
      lat: 46.2,
      lon: 6.14 + at / 100,
    }));
    const differences = () => screen.getByTestId('compare-differences');
    const optionTexts = () => screen.getAllByRole('option').map((option) => option.textContent);

    it('lists the first ten pairs under the table with the heading, the arrows, the names and the caption', async () => {
      mount({ details: { comparison: { pairDifferences: twelve } }, hubs });
      await table();
      const block = within(await screen.findByTestId('compare-differences'));

      expect(block.getByRole('heading')).toHaveTextContent(
        'Hub pairs where the mean bike price differs most: Version C \u2212 Version B',
      );
      const rows = block.getAllByRole('row').slice(1);
      expect(rows).toHaveLength(10);
      expect(
        within(present(rows[0]))
          .getAllByRole('cell')
          .map((c) => c.textContent),
      ).toEqual(['H1 Plainpalais → H20', '1.00', '1.25', '▲ 0.25', '3 000 → 4 500', 'Show on map']);
      expect(within(present(rows[1])).getAllByRole('cell')[3]).toHaveTextContent('▼ 0.30');
      expect(within(present(rows[2])).getAllByRole('cell')[3]).toHaveTextContent(/^0\.00$/);
      expect(within(present(rows[2])).getAllByRole('cell')[0]).toHaveTextContent('H3 → H20');
      expect(
        block.getByRole('columnheader', { name: 'Mean bike price in B (CHF per ride)' }),
      ).toBeVisible();
      expect(block.getByText(/^Mean price per bike ride on the pair, weighted/)).toHaveTextContent(
        "Mean price per bike ride on the pair, weighted by the model's bike rides: a difference mixes a change of price with a change of who rides. Computed from the model's flows.",
      );
      expect(
        screen.getByText(/^Small figures: change against/).compareDocumentPosition(differences()) &
          Node.DOCUMENT_POSITION_FOLLOWING,
      ).toBeTruthy();
    });

    it('draws one pair on the map at a time and removes it on a second click', async () => {
      const { map } = mount({ details: { comparison: { pairDifferences: twelve } }, hubs });
      await table();
      const user = userEvent.setup();
      const buttons = () => within(differences()).getAllByRole('button', { name: 'Show on map' });
      const ids = () => map?.layers.map((layer) => layer.id) ?? [];

      await screen.findByTestId('compare-differences');
      expect(ids()).toEqual(['l4-study-circle', 'l4-hub-outlines', 'l4-hub-discs']);
      await user.click(present(buttons()[0]));
      expect(buttons()[0]).toHaveAttribute('aria-pressed', 'true');
      expect(ids()).toContain('l3-selected-pair');
      expect(map?.layers.find((l) => l.id === 'l4-hub-discs')?.paint['circle-opacity']).toBe(0.35);

      await user.click(present(buttons()[1]));
      expect(buttons()[0]).toHaveAttribute('aria-pressed', 'false');
      expect(buttons()[1]).toHaveAttribute('aria-pressed', 'true');

      await user.click(present(buttons()[1]));
      expect(buttons()[1]).toHaveAttribute('aria-pressed', 'false');
      expect(ids()).not.toContain('l3-selected-pair');
    });

    it('replaces the table by the sentence and titles the card with the flat price when B and C share a solve', async () => {
      mount({ details: { comparison: { identicalSolves: [['B', 'C']] } } });
      await table();

      expect(
        await screen.findByText(
          'Versions B and C have the same pricing model result: no hub pair price differs.',
        ),
      ).toBeVisible();
      expect(screen.queryByText(/Hub pairs where the mean bike price differs most/)).toBeNull();
      expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent(
        /^Versions B and C have the same prices; against a flat price of 1\.00 instead of 1\.00, their simulated car share is /,
      );
    });

    it('offers the three measures, the legend and a redraw when the measure changes', async () => {
      mount({ hubs: sampleHubs });
      await table();
      const user = userEvent.setup();
      const legend = () => screen.getByRole('group', { name: 'Map legend' });

      expect(await screen.findByLabelText('Map shows')).toHaveValue('priceDifference');
      expect(optionTexts()).toEqual([
        'Mean bike price: C \u2212 B',
        'Mean bike price: C \u2212 flat price',
        'Bike rides starting: C \u2212 B',
      ]);
      expect(legend()).toHaveTextContent('Mean bike price: C \u2212 B');
      expect(legend()).toHaveTextContent("computed from the model's flows");
      expect(legend()).toHaveTextContent('+0.15 CHF per ride');

      await user.selectOptions(screen.getByLabelText('Map shows'), 'ridesStartingDifference');
      expect(legend()).toHaveTextContent('Bike rides starting: C \u2212 B');
      expect(legend()).toHaveTextContent('+5 rides');
    });

    it('keeps the measure and the pair shown across a re-read, and drops the pair for other versions', async () => {
      const { map, rerender } = mount({
        details: { comparison: { pairDifferences: twelve } },
        hubs,
      });
      await table();
      const user = userEvent.setup();
      const ids = () => map?.layers.map((layer) => layer.id) ?? [];
      // Found once the re-read has settled: the earlier render under the skeleton is hidden.
      const first = async () =>
        present((await screen.findAllByRole('button', { name: 'Show on map' }))[0]);

      await user.selectOptions(screen.getByLabelText('Map shows'), 'ridesStartingDifference');
      await user.click(await first());
      expect(ids()).toContain('l3-selected-pair');

      // B and C again: the same two versions, read anew.
      rerender(['B', 'C']);
      expect(await first()).toHaveAttribute('aria-pressed', 'true');
      expect(screen.getByLabelText('Map shows')).toHaveValue('ridesStartingDifference');
      expect(ids()).toContain('l3-selected-pair');

      // A and B: another pair of versions, so no pair is shown.
      rerender(['A', 'B']);
      await waitFor(() => {
        expect(screen.getByRole('heading', { name: /Version B − Version A$/ })).toBeVisible();
      });
      expect(await first()).toHaveAttribute('aria-pressed', 'false');
      expect(ids()).not.toContain('l3-selected-pair');
    });
  });
});
