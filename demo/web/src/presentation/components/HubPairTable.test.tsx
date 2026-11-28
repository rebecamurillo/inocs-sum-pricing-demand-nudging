import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import {
  sampleHubPairResults,
  sampleHubResults,
} from '../../application/ports/fake-pricing-gateway';
import { HubPairTable } from './HubPairTable';

function nth<T>(list: readonly T[], at: number): T {
  const found = list[at];
  if (found === undefined) throw new Error(`No element at ${String(at)}.`);
  return found;
}

const labels = new Map(sampleHubResults().map((hub) => [hub.hubId, hub.label]));

function mount(shownPair: string | null = null) {
  const onShowOnMap = vi.fn<(key: string | null) => void>();
  const view = render(
    <HubPairTable
      results={sampleHubPairResults()}
      hubLabels={labels}
      shownPair={shownPair}
      onShowOnMap={onShowOnMap}
    />,
  );
  return { onShowOnMap, ...view };
}

const bodyRows = () => screen.getAllByRole('row').filter((row) => row.hasAttribute('data-state'));

describe('HubPairTable', () => {
  it('lists the columns, the model tag over the travellers and no "Bike" column', () => {
    mount();

    const headers = screen
      .getAllByRole('columnheader')
      .map((header) => header.textContent)
      .join('|');
    for (const name of ['From → to', 'Mean bike price', 'Bike options', 'Car', 'PT', 'PT + bike']) {
      expect(screen.getByRole('button', { name })).toBeVisible();
    }
    expect(screen.queryByRole('button', { name: 'Bike' })).not.toBeInTheDocument();
    expect(headers).toContain("PRICING MODEL'S RESULT");
    expect(screen.getByText('lowest – highest offered')).toBeVisible();
  });

  it('writes the caption verbatim with the computed label', () => {
    mount();
    expect(
      screen.getByText(
        "Mean bike price: per ride, weighted by the model's bike rides on the pair, with the lowest and highest price offered.",
      ),
    ).toBeVisible();
    expect(screen.getByText("computed from the model's flows")).toBeVisible();
  });

  it('shows the three row states', () => {
    mount();

    const [priced, noRides, none] = bodyRows();
    expect(priced).toHaveTextContent('H4 Plainpalais → H9 Eaux-Vives');
    expect(priced).toHaveTextContent('0.95');
    expect(priced).toHaveTextContent('0.60 – 1.40');
    expect(priced).toHaveTextContent('310');
    expect(noRides).toHaveTextContent('— no bike rides');
    expect(noRides).toHaveTextContent('0.70 – 1.20');
    expect(none).toHaveTextContent('no bike option offered');
  });

  it('sorts a column ascending, descending and says so in aria-sort, empty values last', async () => {
    mount();
    const user = userEvent.setup();
    const header = screen.getByRole('columnheader', { name: /^Mean bike price/ });
    expect(header).toHaveAttribute('aria-sort', 'none');

    await user.click(within(header).getByRole('button'));
    expect(header).toHaveAttribute('aria-sort', 'ascending');
    expect(bodyRows()[0]).toHaveTextContent('0.95');
    expect(bodyRows()[2]).toHaveTextContent('no bike option offered');

    await user.click(within(header).getByRole('button'));
    expect(header).toHaveAttribute('aria-sort', 'descending');
    expect(bodyRows()[0]).toHaveTextContent('0.95');

    const car = screen.getByRole('columnheader', { name: 'Car' });
    await user.click(within(car).getByRole('button'));
    expect(header).toHaveAttribute('aria-sort', 'none');
    expect(car).toHaveAttribute('aria-sort', 'ascending');
    expect(bodyRows()[0]).toHaveTextContent('H9 Eaux-Vives → H12 Cornavin');
  });

  it('opens the options of a selected row under it, one at a time, named by their legs', async () => {
    mount();
    const user = userEvent.setup();

    await user.click(nth(bodyRows(), 0));

    const options = screen.getByRole('table', { name: 'Offered bike options' });
    const rows = within(options).getAllByRole('row').slice(1);
    expect(rows).toHaveLength(3);
    expect(rows[0]).toHaveTextContent('Bus 1 → Cornavin · bike Cornavin → Eaux-Vives');
    expect(rows[0]).toHaveTextContent('12 min');
    expect(rows[0]).toHaveTextContent('0.60');
    expect(rows[0]).toHaveTextContent('31');
    expect(rows[2]).toHaveTextContent('Tram 12 → Rive · bike Rive → Eaux-Vives');
    expect(screen.getByText('Option, by its legs')).toBeVisible();
    expect(screen.getByText('Riders in the model')).toBeVisible();
    expect(screen.queryByText(/Bike options offered on/)).not.toBeInTheDocument();

    await user.click(nth(bodyRows(), 1));
    expect(screen.getAllByRole('table', { name: 'Offered bike options' })).toHaveLength(1);
    expect(
      within(screen.getByRole('table', { name: 'Offered bike options' })).getAllByRole('row'),
    ).toHaveLength(2);

    await user.click(nth(bodyRows(), 1));
    expect(screen.queryByRole('table', { name: 'Offered bike options' })).not.toBeInTheDocument();
  });

  it('opens nothing for a pair with no bike option offered, and opens with the keyboard', async () => {
    mount();
    const user = userEvent.setup();

    await user.click(nth(bodyRows(), 2));
    expect(screen.queryByRole('table', { name: 'Offered bike options' })).not.toBeInTheDocument();

    bodyRows()[0]?.focus();
    await user.keyboard('{Enter}');
    expect(screen.getByRole('table', { name: 'Offered bike options' })).toBeVisible();
    expect(bodyRows()[0]).toHaveAttribute('aria-expanded', 'true');
  });

  it('shows a pair on the map without opening the row, and presses the shown one', async () => {
    const { onShowOnMap, rerender } = mount();
    const user = userEvent.setup();

    const buttons = screen.getAllByRole('button', { name: 'Show on map' });
    expect(buttons).toHaveLength(3);
    await user.click(nth(buttons, 0));
    expect(onShowOnMap).toHaveBeenCalledWith('H4>H9');
    expect(screen.queryByRole('table', { name: 'Offered bike options' })).not.toBeInTheDocument();

    rerender(
      <HubPairTable
        results={sampleHubPairResults()}
        hubLabels={labels}
        shownPair="H4>H9"
        onShowOnMap={onShowOnMap}
      />,
    );
    const pressed = screen.getAllByRole('button', { name: 'Show on map' });
    expect(pressed[0]).toHaveAttribute('aria-pressed', 'true');
    expect(pressed[1]).toHaveAttribute('aria-pressed', 'false');
    await user.click(nth(pressed, 0));
    expect(onShowOnMap).toHaveBeenLastCalledWith(null);
  });
});
