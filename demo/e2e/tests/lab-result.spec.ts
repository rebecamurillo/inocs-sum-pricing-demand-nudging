import { buildFakeInstance, builtCounts } from '../support/build';
import { expect, test } from '../support/fixtures';
import {
  createPricingVersion,
  hubPairResultsOf,
  hubResultsOf,
  insightTitle,
  must,
  offeredOptionsOf,
  optionNameOf,
  priceCellOf,
  runToResult,
  simulationOf,
  travellersOf,
  waitForRun,
  waitForSimulationRule,
} from '../support/pricing';

// Its own distance, so no other scenario's build finds this one's routes already computed.
const RESULT_DISTANCE_M = 930;
const PAIRS_DISTANCE_M = 940;
const OLDER_RULE_DISTANCE_M = 935;

/** 72240 → "72 240": a plain space groups the thousands. */
const grouped = (n: number) => String(Math.trunc(n)).replace(/\B(?=(\d{3})+(?!\d))/g, ' ');

test.describe('Result', () => {
  test("L-3 · the result leads with the simulated split with the model's prices against the simulated split with the flat price, labelled as simulation with the rule's name; the model's own split is under 'pricing model's result'", async ({
    page,
    request,
    control,
  }) => {
    const built = await buildFakeInstance(request, control, RESULT_DISTANCE_M);
    const draft = await createPricingVersion(request, built.version, { name: 'Incentive' });
    const result = await runToResult(request, draft.id);

    const withPrices = simulationOf(result, 'model_prices');
    const flat = simulationOf(result, 'flat');
    const { car: versionCar, ptOnly: versionPt, ptBike: versionBike } = withPrices;
    const { car: flatCar, ptOnly: flatPt, ptBike: flatBike } = flat;
    const travellers = versionCar + versionPt + versionBike + withPrices.unserved;

    await page.goto(`/#/lab/${built.version}/result/${draft.letter}`);
    await page.reload();
    const main = page.getByRole('main');

    // The brief, its sentence, the scope; no tag heads the screen.
    await expect(main.getByText('Result · pipeline step 6')).toBeVisible();
    await expect(
      main.getByText(
        "The pricing model's prices for the period, and the same travellers simulated twice: with these prices and with a flat bike price.",
      ),
    ).toBeVisible();
    await expect(main.getByText(/^Version A · Incentive · Geneva 3 km v1 · .+$/)).toBeVisible();

    // The SIMULATION group.
    const simulation = page.getByTestId('simulation-group');
    await expect(simulation.getByText('SIMULATION', { exact: true })).toBeVisible();
    await expect(
      simulation.getByText('Simulated travellers · placeholder rule: half price, half travel time'),
    ).toBeVisible();
    const fewer = Math.round(((flatCar - versionCar) * 100) / travellers);
    const insight = insightTitle('A', fewer);
    await expect(simulation.getByRole('heading', { level: 2 })).toHaveText(insight);

    const flatAmount = (await (
      await request.get(`/api/v1/pricing-versions/${draft.id}`)
    ).json()) as {
      goals: { flat_price_per_ride_chf: number };
    };
    const flatLabel = `With a flat price ${flatAmount.goals.flat_price_per_ride_chf.toFixed(2)} CHF`;
    await expect(simulation.getByText("With Version A's prices", { exact: true })).toBeVisible();
    await expect(simulation.getByText(flatLabel, { exact: true })).toBeVisible();
    await expect(
      simulation.getByRole('img', {
        name: `With Version A's prices: Car ${grouped(versionCar)}, Public transport ${grouped(versionPt)}, Public transport + shared bike ${grouped(versionBike)}`,
      }),
    ).toBeVisible();
    await expect(
      simulation.getByRole('img', {
        name: `${flatLabel}: Car ${grouped(flatCar)}, Public transport ${grouped(flatPt)}, Public transport + shared bike ${grouped(flatBike)}`,
      }),
    ).toBeVisible();
    await expect(simulation.getByRole('list', { name: 'Modes' }).getByRole('listitem')).toHaveText([
      '🚗Car',
      '🚋Public transport',
      '🚋+🚲Public transport + shared bike',
    ]);
    const caption = simulation.getByText(/^Each of the /);
    await expect(caption).toHaveText(
      `Each of the ${grouped(travellers)} travellers of the period takes the option that scores best on half price, half travel time, while a bike and a dock remain at its stations. ${grouped(withPrices.displaced)} did not get their first choice (no bike or dock); ${grouped(flat.displaced)} with the flat price. Travellers left with no option: ${grouped(withPrices.unserved)} · ${grouped(flat.unserved)}. A placeholder until the model's author defines the simulation. The pricing model prices a shared bike only together with a public transport trip: trips by shared bike alone are not part of these results.`,
    );

    // The model's own split: blue tag, title, one bar on the same scale, the sentence.
    const model = page.getByTestId('model-group');
    await expect(model.getByText("PRICING MODEL'S RESULT")).toBeVisible();
    await expect(model.getByText("The pricing model's own split")).toBeVisible();
    await expect(model.getByRole('img', { name: /^Version A, pricing model: Car / })).toBeVisible();
    await expect(model.getByText(/^Why it differs from the simulated split: /)).toBeVisible();
    // A simulated number never sits under the blue tag, nor a model number under the grey one.
    await expect(model.getByText('SIMULATION', { exact: true })).toHaveCount(0);
    await expect(model.getByText(/Simulated travellers/)).toHaveCount(0);
    await expect(simulation.getByText("PRICING MODEL'S RESULT")).toHaveCount(0);

    // Top to bottom: simulation, model, goals.
    const boxes = await Promise.all([
      simulation.boundingBox(),
      model.boundingBox(),
      page.getByRole('heading', { name: 'The three goals of this version' }).boundingBox(),
    ]);
    const [top, middle, bottom] = boxes.map((box) => box?.y ?? Number.NaN);
    expect(top).toBeLessThan(middle ?? 0);
    expect(middle).toBeLessThan(bottom ?? 0);

    // The four tiles, every figure the route's value, formatted.
    const profit = page.getByTestId('tile-profit');
    const ridershipTile = page.getByTestId('tile-ridership');
    const balance = page.getByTestId('tile-station_balance');
    const price = page.getByTestId('tile-average_bike_price');
    await expect(profit).toContainText('weight 1 · fixed');
    await expect(ridershipTile).toContainText('weight 8.00');
    await expect(balance).toContainText('stations empty or full at 09:00');
    await expect(price).toContainText('Average bike price');
    await expect(
      main.getByText('simulated travellers · placeholder rule', { exact: true }),
    ).toHaveCount(4);
    const ridership = result.goals.find((goal) => goal.name === 'ridership');
    expect(ridership?.model_prices).not.toBeNull();
    await expect(ridershipTile.getByText(/^[\d ]+$/)).toHaveText(
      grouped(Math.round(ridership?.model_prices?.value ?? Number.NaN)),
    );
    await expect(ridershipTile).toContainText(
      `Pricing model: ${grouped(Math.round(ridership?.model?.value ?? Number.NaN))}`,
    );
  });

  test("L-3 · the hub-pair table lists price and travellers per pair; Advanced view adds the solver's numbers", async ({
    page,
    request,
    control,
  }) => {
    const built = await buildFakeInstance(request, control, PAIRS_DISTANCE_M);
    const counts = await builtCounts(request, built.version);
    const draft = await createPricingVersion(request, built.version, { name: 'Incentive' });
    const result = await runToResult(request, draft.id);
    const { advanced } = result;
    const pairs = await hubPairResultsOf(request, draft.id);
    const hubs = await hubResultsOf(request, draft.id);
    const label = (id: string) => hubs.find((hub) => hub.hub_id === id)?.label ?? id;
    const withBike = pairs.filter((pair) => pair.min_bike_price !== null).length;
    const whole = (n: number) => grouped(Math.round(n));
    const money = (n: number) => n.toFixed(2);

    await page.goto(`/#/lab/${built.version}/result/${draft.letter}`);
    await page.reload();
    const main = page.getByRole('main');

    // The link counts the pairs with routes and those with a bike option offered.
    const link = main.getByRole('button', { name: /^Price and flow per hub pair \(/ });
    await expect(link).toHaveText(
      `▸ Price and flow per hub pair (${grouped(counts.hub_pairs_with_routes ?? 0)} hub pairs, ${grouped(withBike)} with a bike option offered)`,
    );
    await link.click();

    const table = main.getByRole('table', { name: 'Price and flow per hub pair' });
    await expect(table).toBeVisible();
    for (const heading of [
      'From → to',
      'Mean bike price',
      'Bike options',
      'Car',
      'PT',
      'PT + bike',
    ]) {
      await expect(table.getByRole('button', { name: heading, exact: true })).toBeVisible();
    }
    await expect(table.getByRole('button', { name: 'Bike', exact: true })).toHaveCount(0);
    await expect(table.getByText("PRICING MODEL'S RESULT")).toBeVisible();
    await expect(
      main.getByText(
        "Mean bike price: per ride, weighted by the model's bike rides on the pair, with the lowest and highest price offered.",
      ),
    ).toBeVisible();
    await expect(main.getByText("computed from the model's flows", { exact: true })).toBeVisible();

    // The rows are the route's rows, in its order, with its figures formatted as the screen does.
    const rows = table.getByRole('row').filter({ hasText: 'Show on map' });
    await expect(rows).toHaveCount(pairs.length);
    const first = must(pairs[0], 'the first hub pair');
    const cells = rows.first().getByRole('cell');
    const travellers = travellersOf(first);
    await expect(cells.nth(0)).toHaveText(
      `${label(first.origin_hub)} → ${label(first.destination_hub)}`,
    );
    await expect(cells.nth(1)).toContainText(priceCellOf(first));
    await expect(cells.nth(3)).toHaveText(whole(travellers.car));
    await expect(cells.nth(4)).toHaveText(whole(travellers.pt));
    await expect(cells.nth(5)).toHaveText(whole(travellers.ptBike));

    // A row with offered options opens them under it, named by their legs.
    const open = must(
      pairs.find((pair) => offeredOptionsOf(pair).length > 0),
      'a hub pair with an offered bike option',
    );
    const expected = offeredOptionsOf(open);
    await rows
      .filter({ hasText: `${label(open.origin_hub)} → ${label(open.destination_hub)}` })
      .first()
      .click();
    const options = main.getByRole('table', { name: 'Offered bike options' });
    const optionRows = options.getByRole('row').filter({ hasNotText: 'Option, by its legs' });
    await expect(optionRows).toHaveCount(expected.length);
    for (const [at, option] of expected.entries()) {
      const row = optionRows.nth(at);
      await expect(row.getByRole('cell').nth(0)).toHaveText(optionNameOf(option.legs));
      await expect(row.getByRole('cell').nth(1)).toHaveText(
        `${String(Math.round(option.duration.value / 60))} min`,
      );
      await expect(row.getByRole('cell').nth(3)).toHaveText(money(option.bike_price?.value ?? 0));
    }

    // A column sorts and says so.
    const price = table.getByRole('columnheader', { name: /^Mean bike price/ });
    await price.getByRole('button').click();
    await expect(price).toHaveAttribute('aria-sort', 'ascending');
    await price.getByRole('button').click();
    await expect(price).toHaveAttribute('aria-sort', 'descending');

    // The map: the legend of the selected measure, then another.
    const legend = page.getByRole('group', { name: 'Map legend' });
    await expect(legend).toHaveText(
      /^Bike rides starting at each hub, \d\d:\d\d–\d\d:\d\d · One disc per hub; a bike ride is one bike leg\. Computed from the model's flows\.few.*many$/,
    );
    await page
      .getByRole('combobox', { name: 'Map shows' })
      .selectOption({ label: 'Bike rides ending at each hub' });
    await expect(legend).toContainText(/^Bike rides ending at each hub, \d\d:\d\d–\d\d:\d\d · /);

    // "Show on map" presses one pair; "Hide map" gives the card the whole width.
    const show = rows.first().getByRole('button', { name: 'Show on map' });
    await show.click();
    await expect(show).toHaveAttribute('aria-pressed', 'true');
    await show.click();
    await expect(show).toHaveAttribute('aria-pressed', 'false');
    const map = page.getByRole('region', { name: 'Map' });
    await expect(map).toBeVisible();
    await page.getByRole('button', { name: 'Hide map' }).click();
    await expect(map).toBeHidden();
    await page.getByRole('button', { name: 'Show map' }).click();
    await expect(map).toBeVisible();

    // Advanced view: absent with the switch off, present with it on, and remembered on reload.
    const title = main.getByRole('heading', { level: 2, name: 'Advanced view' });
    await expect(title).toHaveCount(0);
    await page.getByRole('switch', { name: 'Advanced view' }).click();
    await expect(title).toBeVisible();
    await page.reload();
    await expect(page.getByRole('switch', { name: 'Advanced view' })).toHaveAttribute(
      'aria-checked',
      'true',
    );
    await expect(title).toBeVisible();

    const group = (name: string) => main.getByRole('region', { name, exact: true });
    const cell = (name: string, label: string) =>
      group(name)
        .getByRole('row')
        .filter({ has: page.getByRole('rowheader', { name: label, exact: true }) })
        .getByRole('cell');
    const number = (name: string) => advanced.numbers[name]?.value;
    const textOf = (value: number | undefined, show: (n: number) => string) =>
      value === undefined ? '—' : show(value);

    // What the solver maximised: a term is listed only when the API returns it (the residual
    // check passed), and the objective value always is.
    const objective = 'What the solver maximised';
    const terms = [
      ['objective_term_ridership', 'Ridership term'],
      ['objective_term_revenue', '+ Revenue'],
      ['objective_term_cost', '− Cost'],
      ['objective_term_station_balance', '+ Station balance term'],
    ] as const;
    await expect(
      group(objective).getByRole('rowheader', {
        name: /^(Ridership term|\+ Revenue|− Cost|\+ Station balance term)$/,
      }),
    ).toHaveCount(terms.filter(([name]) => number(name) !== undefined).length);
    for (const [name, label] of terms.filter(([key]) => number(key) !== undefined)) {
      await expect(cell(objective, label)).toHaveText(textOf(number(name), whole));
    }
    await expect(cell(objective, '= Objective value')).toContainText(
      textOf(number('objective_value'), whole),
    );
    await expect(cell(objective, '= Objective value')).toContainText("PRICING MODEL'S RESULT");

    // The solver's numbers, as the screen words them.
    await expect(cell('Solver', 'Solution time')).toHaveText(
      textOf(number('solution_time_s'), (n) => `${n.toFixed(1)} s`),
    );
    await expect(cell('Solver', 'Optimality gap')).toHaveText(
      textOf(number('gap_pct'), (n) => `${n.toFixed(2)} %`),
    );
    await expect(cell('Solver', 'Status')).toHaveText(
      { OPTIMAL: 'optimal', SUBOPTIMAL: 'suboptimal', TIME_LIMIT: 'stopped with a solution' }[
        advanced.solver_status_name
      ] ?? advanced.solver_status_name.toLowerCase().replaceAll('_', ' '),
    );
    await expect(cell('Solver', 'Hub pairs · bike options offered')).toHaveText(
      `${grouped(counts.hub_pairs_with_routes ?? 0)} · ${grouped(
        pairs.reduce((sum, pair) => sum + offeredOptionsOf(pair).length, 0),
      )}`,
    );
    await expect(cell('Solver', 'Stopped before the search ended')).toHaveText(
      number('time_limit_reached') === 1 ? 'yes' : 'no',
    );

    // The simulation: the rule and each scheme's figures.
    const [modelPrices, flat] = [
      must(
        result.simulations.find((item) => item.price_scheme === 'model_prices'),
        'the simulation with the model prices',
      ),
      must(
        result.simulations.find((item) => item.price_scheme === 'flat'),
        'the simulation with the flat price',
      ),
    ];
    const weight = (name: string) => String(modelPrices.rule_parameters[name]);
    await expect(group('Traveller simulation')).toContainText(
      `Rule: ${modelPrices.rule_id} v${String(modelPrices.rule_version)} · price weight ${weight('price_weight')} · time weight ${weight('time_weight')} · placeholder`,
    );
    await expect(
      cell('Traveller simulation', 'Bike rides · with these prices / with the flat price'),
    ).toHaveText(`${whole(modelPrices.bike_rides.value)} / ${whole(flat.bike_rides.value)}`);
    const profit = (item: typeof modelPrices) => whole(item.revenue.value - item.cost.value);
    await expect(
      cell('Traveller simulation', 'Revenue − cost · with these prices / with the flat price'),
    ).toHaveText(`${profit(modelPrices)} / ${profit(flat)}`);
    await expect(group('Traveller simulation')).toContainText(
      'A bike ride is one bike leg; an option with two bike legs counts two rides',
    );

    // About this result.
    const about = 'About this result';
    const provenance = result.provenance;
    expect(provenance.timetable_operator).toBe('tpg');
    await expect(cell(about, 'Pricing model')).toHaveText(
      `package ${provenance.package_version ?? 'not recorded'} · commit ${provenance.package_commit?.slice(0, 7) ?? 'not recorded'}`,
    );
    await expect(cell(about, 'Solver')).toHaveText(
      new RegExp(
        `^Gurobi ${provenance.gurobi_version} · ${provenance.licence_kind === 'full' ? 'full' : 'size-limited'} licence · status `,
      ),
    );
    await expect(cell(about, 'Timetable')).toHaveText(
      /^tpg · valid .+ to .+ · routes planned for /,
    );
    await expect(cell(about, 'Bike stations')).toHaveText(
      new RegExp(
        `^${new URL(provenance.bike_stations_source_url ?? '').host.replaceAll('.', '\\.')} · fetched `,
      ),
    );
    await expect(cell(about, 'Simulation')).toHaveText(
      new RegExp(
        `^${modelPrices.rule_id} v${String(modelPrices.rule_version)} · \\d{1,2} [A-Z][a-z]{2} \\d{4}$`,
      ),
    );
    await expect(cell(about, 'Demonstrator')).toHaveText(provenance.demonstrator_version);

    // No screen names a solver time limit.
    expect((await page.content()).toLowerCase()).not.toContain('time limit');
  });

  test("L-3 · a version simulated with an older rule names that rule; simulating it again adds the current rule's numbers without solving, with the solver unavailable", async ({
    page,
    request,
    control,
  }) => {
    const built = await buildFakeInstance(request, control, OLDER_RULE_DISTANCE_M);
    const draft = await createPricingVersion(request, built.version);
    await runToResult(request, draft.id);
    await waitForSimulationRule(request, 1);
    const before = (await (await request.get(`/api/v1/pricing-versions/${draft.id}`)).json()) as {
      run_id: string;
    };

    // A new rule version, the simulation held at its step, and no solver: a simulation reads the
    // stored solve.
    await control.setPricingModel({
      simulation_rule: { version: 2, price_weight: 0.6, time_weight: 0.4 },
      hold_at: 'traveller_simulation',
    });
    await control.makeUnavailable('solver', 'The Gurobi licence is not available.');
    await waitForSimulationRule(request, 2);

    await page.goto(`/#/lab/${built.version}/result/${draft.letter}`);
    await page.reload();
    const main = page.getByRole('main');
    const menu = page.getByRole('complementary', { name: 'Menu' });
    const box = page.getByTestId('older-rule');
    await expect(
      box.getByText(
        "Simulated with an older rule. These simulations used the placeholder rule v1; the Lab now simulates with v2. The pricing model's numbers do not change.",
      ),
    ).toBeVisible();
    const simulation = page.getByTestId('simulation-group');
    await expect(
      simulation.getByText(
        'Simulated travellers · placeholder rule: half price, half travel time · older rule (v1)',
      ),
    ).toBeVisible();
    const older = (await (
      await request.get(`/api/v1/pricing-versions/${draft.id}/result`)
    ).json()) as Parameters<typeof simulationOf>[0];
    const olderCar = simulationOf(older, 'model_prices').car;
    const barOf = (car: number) =>
      simulation.getByRole('img', {
        name: new RegExp(`^With Version A's prices: Car ${grouped(car)},`),
      });
    await expect(barOf(olderCar)).toBeVisible();

    // Simulate again: the row and the box say so, the old figures stay.
    await box.getByRole('button', { name: 'Simulate again with v2' }).click();
    await expect(menu.getByRole('button', { name: /Version A .*● simulating$/ })).toBeVisible({
      timeout: 30_000,
    });
    await expect(box.getByText(/Traveller simulation · running for \d+ s/)).toBeVisible({
      timeout: 30_000,
    });
    await expect(box.getByRole('button')).toHaveCount(0);
    await expect(barOf(olderCar)).toBeVisible();
    await page.getByRole('switch', { name: 'Advanced view' }).click();
    await expect(
      main.getByText('Earlier simulations of this version', { exact: true }),
    ).toBeVisible();

    // The run ends: the figures are those of the result route (rule 2), the box goes.
    const [simulationRun] = await control.activeRunIds();
    expect(simulationRun).toBeDefined();
    await control.releaseRun(simulationRun ?? '');
    const ended = await waitForRun(request, simulationRun ?? '', 'succeeded');
    expect(ended.kind).toBe('simulation');
    expect(ended.steps.map((step) => step.step)).toEqual(['traveller_simulation']);
    await expect(page.getByTestId('older-rule')).toHaveCount(0);
    const current = (await (
      await request.get(`/api/v1/pricing-versions/${draft.id}/result`)
    ).json()) as Parameters<typeof simulationOf>[0];
    expect(current.simulations.every((item) => item.rule_version === 2)).toBe(true);
    await expect(barOf(simulationOf(current, 'model_prices').car)).toBeVisible();
    await expect(simulation.getByText(/· older rule \(v/)).toHaveCount(0);
    await expect(menu.getByRole('button', { name: /Version A .*✓ result$/ })).toBeVisible();
    const after = (await (await request.get(`/api/v1/pricing-versions/${draft.id}`)).json()) as {
      run_id: string;
    };
    expect(after.run_id).toBe(before.run_id);

    // "Duplicate" opens the next draft's L-2; "Delete…" asks first and "Keep" closes it.
    await main.getByRole('button', { name: 'Duplicate' }).click();
    await expect(page).toHaveURL(new RegExp(`#/lab/${built.version}/pricing/B$`));
    await page.goto(`/#/lab/${built.version}/result/${draft.letter}`);
    await main.getByRole('button', { name: 'Delete…' }).click();
    await expect(
      main.getByText(
        'Delete Version A · Version A? This removes its goals and its result. Other versions of Geneva 3 km v1 stay. This cannot be undone.',
      ),
    ).toBeVisible();
    await main.getByRole('button', { name: 'Keep' }).click();
    await expect(main.getByRole('button', { name: 'Delete Version A' })).toHaveCount(0);
    expect((await request.get(`/api/v1/pricing-versions/${draft.id}`)).status()).toBe(200);
  });
});
