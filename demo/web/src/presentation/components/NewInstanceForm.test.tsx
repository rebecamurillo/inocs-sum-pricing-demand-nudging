import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { CityInstanceGateway } from '../../application/ports/city-instance-gateway';
import { fakeCityInstances, sampleDraft } from '../../application/ports/fake-city-instance-gateway';
import type { Gateways } from '../../application/ports/gateways';
import type { CityDataset } from '../../domain/map';
import type { LabRoute } from '../../domain/route';
import { GatewaysProvider } from '../hooks/gateways';
import { NewInstanceForm } from './NewInstanceForm';

const dataset: CityDataset = {
  id: 'geneva-2026-11-26',
  centre: { lat: 46.2, lon: 6.14 },
  radiusM: 3000,
  availableArea: [6, 46, 6.3, 46.4],
};

function mount(
  overrides: Partial<CityInstanceGateway> = {},
  onNavigate: (route: LabRoute) => void = () => undefined,
  datasets: CityDataset[] = [dataset],
) {
  const gateways: Gateways = {
    systemStatus: { load: () => Promise.reject(new Error('not called')) },
    layoutPreferences: { load: vi.fn(), save: vi.fn() },
    cityDatasets: { list: () => Promise.resolve(datasets) },
    basemap: { exists: () => Promise.resolve(false), url: () => '' },
    cityInstances: fakeCityInstances(overrides),
  };
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <GatewaysProvider gateways={gateways}>
        <NewInstanceForm onNavigate={onNavigate} />
      </GatewaysProvider>
    </QueryClientProvider>,
  );
}

const name = () => screen.getByRole('textbox', { name: 'Name' });

describe('NewInstanceForm', () => {
  it('shows only Name, City data and Start from, with a copy per saved version', async () => {
    mount();

    expect(await screen.findByRole('heading', { name: 'New city instance' })).toBeInTheDocument();
    expect(name()).toHaveValue('');
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
    expect(
      within(start)
        .getAllByRole('option')
        .map((option) => option.textContent),
    ).toEqual([
      "The model package's default values",
      'A copy of Geneva 3 km v1',
      'A copy of Geneva 2 km v1',
    ]);
    expect(
      screen.queryByRole('region', { name: 'Rules checked before saving' }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('offers no copy when there is no saved version', async () => {
    mount({ menu: () => Promise.resolve([]) });

    const start = await screen.findByRole('combobox', { name: 'Start from' });

    expect(within(start).getAllByRole('option')).toHaveLength(1);
  });

  it('posts once when Name loses focus and opens the draft', async () => {
    const createInstance = vi.fn(() =>
      Promise.resolve({
        kind: 'created' as const,
        version: { ...sampleDraft, id: 'geneva-4km.v1', instanceId: 'geneva-4km', number: 1 },
      }),
    );
    const onNavigate = vi.fn();
    mount({ createInstance }, onNavigate);
    const user = userEvent.setup();
    await screen.findByRole('heading', { name: 'New city instance' });

    await user.type(name(), ' Geneva 4 km ');
    expect(createInstance).not.toHaveBeenCalled();
    await user.tab();

    await waitFor(() => {
      expect(onNavigate).toHaveBeenCalledWith({
        kind: 'instance',
        instance: { instanceId: 'geneva-4km', version: 1 },
        period: null,
      });
    });
    expect(createInstance).toHaveBeenCalledTimes(1);
    expect(createInstance).toHaveBeenCalledWith('Geneva 4 km', 'geneva-2026-11-26', {
      kind: 'package_defaults',
    });
  });

  it('posts once on Enter followed by the blur, and sends the copy chosen', async () => {
    const createInstance = vi.fn(() =>
      Promise.resolve({ kind: 'created' as const, version: { ...sampleDraft, number: 1 } }),
    );
    mount({ createInstance });
    const user = userEvent.setup();
    const start = await screen.findByRole('combobox', { name: 'Start from' });
    await user.selectOptions(start, 'A copy of Geneva 2 km v1');

    await user.type(name(), 'Geneva 4 km{Enter}');
    await user.tab();

    await waitFor(() => {
      expect(createInstance).toHaveBeenCalledTimes(1);
    });
    expect(createInstance).toHaveBeenCalledWith('Geneva 4 km', 'geneva-2026-11-26', {
      kind: 'copy',
      versionId: 'geneva-2km.v1',
    });
  });

  it('sends nothing for an empty name', async () => {
    const createInstance = vi.fn();
    mount({ createInstance });
    const user = userEvent.setup();
    await screen.findByRole('heading', { name: 'New city instance' });

    await user.click(name());
    await user.tab();
    await user.type(name(), '   {Enter}');

    expect(createInstance).not.toHaveBeenCalled();
  });

  it('shows the detail of a used name as the note and creates nothing', async () => {
    const createInstance = vi.fn(() =>
      Promise.resolve({
        kind: 'name_taken' as const,
        detail: 'A city instance named Geneva 3 km already exists.',
      }),
    );
    const onNavigate = vi.fn();
    mount({ createInstance }, onNavigate);
    const user = userEvent.setup();
    await screen.findByRole('heading', { name: 'New city instance' });

    await user.type(name(), 'Geneva 3 km{Enter}');

    expect(
      await screen.findByText('A city instance named Geneva 3 km already exists.'),
    ).toBeInTheDocument();
    expect(onNavigate).not.toHaveBeenCalled();
    // Another name is sent again.
    await user.clear(name());
    await user.type(name(), 'Geneva 5 km{Enter}');
    await waitFor(() => {
      expect(createInstance).toHaveBeenCalledTimes(2);
    });
  });

  it('says there is no city data when none is imported', async () => {
    mount({}, () => undefined, []);

    expect(
      await screen.findByText(
        "No city data is imported yet. A city instance needs a timetable and bike stations; the maintainer imports Geneva's with one command (demo/README.md).",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByRole('textbox', { name: 'Name' })).not.toBeInTheDocument();
  });
});
