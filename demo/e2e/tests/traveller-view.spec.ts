import { buildFakeInstance } from '../support/build';
import { expect, test } from '../support/fixtures';
import { finishVersion } from '../support/pricing';
import { pricedPair, quotedHubs, quoteOf, sameHubPair } from '../support/trips';

// Its own distance, so no other scenario's build finds this one's routes already computed.
const TRAVELLER_DISTANCE_M = 915;

test.describe('Traveller view', () => {
  test('L-5 · two points priced by version B; switching to C changes the prices; points in one hub and outside the zone show their messages', async ({
    page,
    request,
    control,
  }) => {
    const built = await buildFakeInstance(request, control, TRAVELLER_DISTANCE_M);
    await finishVersion(request, built.version, 'Baseline');
    await finishVersion(request, built.version, 'Incentive', {
      pt_fare_chf: 3,
      car_parking_fee_chf: 4,
      lowest_price_chf: 0.8,
    });
    await finishVersion(request, built.version, 'Steeper', {
      pt_fare_chf: 4,
      car_parking_fee_chf: 5,
      lowest_price_chf: 1.2,
      ridership_weight: 20,
    });

    const [stopA, stopB] = await pricedPair(request, built.version, `${built.version}.B`);
    const { prices: pricesB } = await quoteOf(request, `${built.version}.B`, stopA, stopB);
    const { prices: pricesC } = await quoteOf(request, `${built.version}.C`, stopA, stopB);

    // The menu item opens the first finished version: its link, the brief and the three rows.
    await page.goto('/');
    await page.reload();
    await page.getByRole('button', { name: 'Trip options and prices' }).click();
    await expect(page).toHaveURL(new RegExp(`#/lab/traveller/${built.version}/A$`));
    const main = page.getByRole('main');
    await expect(main.getByText('Traveller view', { exact: true })).toBeVisible();
    await expect(main.getByRole('heading', { level: 2 })).toHaveText([
      'Pricing version',
      'Trip',
      'Time slot',
    ]);
    const versions = main.getByRole('combobox', { name: 'Pricing version' });
    await expect(versions.getByRole('option')).toHaveText([
      'Geneva 3 km v1 · Version A · Baseline',
      'Geneva 3 km v1 · Version B · Incentive',
      'Geneva 3 km v1 · Version C · Steeper',
    ]);
    await expect(
      main.getByText(/^Gives the city instance \(its \d+ hubs and \d+ bike stations/),
    ).toBeVisible();
    await expect(main.getByRole('combobox', { name: 'Day' }).getByRole('option')).toHaveText([
      'Monday',
    ]);
    const periods = main.getByRole('combobox', { name: 'Period' }).getByRole('option');
    await expect(periods).toHaveCount(17);
    await expect(periods.first()).toHaveText('06:00–07:00 · no prices in this version');
    await expect(periods.nth(2)).toHaveText('08:00–09:00');
    await expect(main.getByText('NEXT VERSION')).toBeVisible();

    // Version B, then two typed stop names of different hubs.
    await versions.selectOption(`${built.version}.B`);
    await expect(page).toHaveURL(new RegExp(`#/lab/traveller/${built.version}/B$`));
    const fieldA = main.getByRole('combobox', { name: 'Point A' });
    const fieldB = main.getByRole('combobox', { name: 'Point B' });
    await fieldA.fill(stopA.name);
    const listA = main.getByRole('listbox');
    await expect(listA.getByRole('option').first()).toHaveText(
      `${stopA.name} · stop · hub ${stopA.hub_id}`,
    );
    await listA.getByRole('option').first().click();
    await fieldB.fill(stopB.name);
    await expect(main.getByRole('listbox').getByRole('option').first()).toBeVisible();
    await fieldB.press('ArrowDown');
    await fieldB.press('Enter');
    await expect(fieldA).toHaveValue(new RegExp(`^hub ${stopA.hub_id} · .+`));
    await expect(fieldB).toHaveValue(new RegExp(`^hub ${stopB.hub_id} · .+`));
    await expect(main.getByText('Monday 08:00–09:00 · Version B')).toBeVisible();
    for (const [label, mode] of [
      ['Car', 'car'],
      ['Public transport + shared bike', 'pt_bike'],
      ['Public transport', 'pt_only'],
    ] as const) {
      const row = main.getByTestId(`card-${mode}`);
      await expect(row).toContainText(label);
      await expect(row).toContainText(pricesB[mode] ?? 'no price');
      await expect(row.getByRole('deletion')).toHaveCount(0);
    }

    // Version C: new prices, the previous ones struck through, the route pushed.
    await versions.selectOption(`${built.version}.C`);
    await expect(page).toHaveURL(new RegExp(`#/lab/traveller/${built.version}/C$`));
    await expect(main.getByText('Monday 08:00–09:00 · Version C')).toBeVisible();
    for (const mode of ['car', 'pt_bike', 'pt_only']) {
      const row = main.getByTestId(`card-${mode}`);
      await expect(row.getByRole('deletion')).toHaveText(pricesB[mode] ?? 'no price');
      await expect(main.getByTestId(`price-${mode}`)).toContainText(pricesC[mode] ?? 'no price');
    }

    // Back restores B; a reload keeps the chosen version.
    await page.goBack();
    await expect(versions).toHaveValue(`${built.version}.B`);
    await page.goForward();
    await page.reload();
    await expect(versions).toHaveValue(`${built.version}.C`);
    await expect(main.getByRole('combobox', { name: 'Period' })).toHaveValue('mon-08');

    // L-3's secondary action opens L-5 with that version.
    await page.goto(`/#/lab/${built.version}/result/B`);
    await page.reload();
    await page.getByRole('button', { name: 'Open in the traveller view' }).click();
    await expect(page).toHaveURL(new RegExp(`#/lab/traveller/${built.version}/B$`));
    await expect(versions).toHaveValue(`${built.version}.B`);

    // The messages part runs from stored data: the solver and the trip planner are unavailable.
    await control.makeUnavailable('solver', 'Solver unavailable for the scenario');
    await control.makeUnavailable('trip_planner', 'Trip planner unavailable for the scenario');
    await page.goto(`/#/lab/traveller/${built.version}/B`);
    await page.reload();
    await fieldA.fill(stopA.name);
    await main.getByRole('listbox').getByRole('option').first().click();
    await fieldB.fill(stopB.name);
    await main.getByRole('listbox').getByRole('option').first().click();
    const { origin, destination } = await quotedHubs(request, `${built.version}.B`, stopA, stopB);
    await expect(
      main.getByRole('heading', {
        name: `Priced between hub ${origin.hub_id} (${origin.hub_name}) and hub ${destination.hub_id} (${destination.hub_name})`,
      }),
    ).toBeVisible();
    await expect(main.getByText('Monday 08:00–09:00 · Version B')).toBeVisible();
    await expect(main.getByTestId(/^card-/)).toHaveCount(3);
    await expect(main.getByTestId('card-car')).toContainText('Car');
    await expect(main.getByTestId('card-pt_bike')).toContainText('Public transport + shared bike');
    await expect(main.getByTestId('card-pt_only')).toContainText('Public transport');
    await expect(main.getByTestId('card-pt_bike')).toContainText('SET BY THE PRICING MODEL');
    const notes = main.getByText(
      /^(The bike price is|The pricing model prices a shared bike|Durations and legs are those)/,
    );
    await expect(notes).toHaveText([
      "The bike price is the pricing model's price for this option, per bike ride, added to the public transport fare. Durations and legs: trip planner, between the two hubs.",
      'The pricing model prices a shared bike only together with a public transport trip: a trip by shared bike alone has no option here.',
      'Durations and legs are those of the hub pair: the walk from your point to the hub is not included.',
    ]);
    await expect(main.getByRole('alert')).toHaveCount(0);

    // Two typed stop names of one hub.
    const [sameA, sameB] = await sameHubPair(request, built.version);
    await fieldA.fill(sameA.name);
    await main.getByRole('listbox').getByRole('option').first().click();
    await fieldB.fill(sameB.name);
    await main.getByRole('listbox').getByRole('option').first().click();
    await expect(main.getByRole('status')).toHaveText(
      `No model price for this trip: both points are in hub ${sameA.hub_id}. The model prices trips between hubs.`,
    );
    await expect(main.getByTestId('card-car')).toHaveCount(0);

    // A click near a corner of the map pane: outside the fitted study circle.
    const instance = (await (
      await request.get(`/api/v1/instance-versions/${built.version}`)
    ).json()) as { parameters: { radius_m: number } };
    const radiusKm = String(instance.parameters.radius_m / 1000);
    await fieldB.focus();
    await page.getByRole('region', { name: 'Map' }).click({ position: { x: 6, y: 6 } });
    await expect(main.getByRole('status')).toHaveText(
      `Point B is outside the ${radiusKm} km zone of Geneva 3 km v1.`,
    );
    await expect(main.getByRole('alert')).toHaveCount(0);
  });
});
