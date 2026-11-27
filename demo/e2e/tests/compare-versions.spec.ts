import { buildFakeInstance } from '../support/build';
import { expect, test } from '../support/fixtures';
import { finishVersion } from '../support/pricing';

// Its own distance, so no other scenario's build finds this one's routes already computed.
const COMPARE_DISTANCE_M = 925;
const SAME_RESULT_DISTANCE_M = 930;

const THREE_MODES =
  'The pricing model prices a shared bike only together with a public transport trip: trips by shared bike alone are not part of these results.';

test.describe('Compare versions', () => {
  test('L-4 · three versions side by side mark the best value per row; the CSV holds names and goals', async ({
    page,
    request,
    control,
  }) => {
    const built = await buildFakeInstance(request, control, COMPARE_DISTANCE_M);
    await finishVersion(request, built.version, 'Baseline');
    // Only the goals the flat simulation does not read differ: one flat column serves all three.
    await finishVersion(request, built.version, 'Heavier ridership', { ridership_weight: 20 });
    await finishVersion(request, built.version, 'Higher floor', { lowest_price_chf: 0.9 });
    // The fake city sends every simulated traveller by public transport whatever the goals, so
    // no value is better than another: the answer's car shares are set here, as the API would
    // mark them when Version C has the lowest.
    await page.route('**/api/v1/comparisons?*', async (route) => {
      const answer = (await (await route.fetch()).json()) as {
        groups: {
          name: string;
          rows: {
            key: string;
            best: string[];
            values: Record<string, { value: number } | null>;
          }[];
        }[];
      };
      const row = answer.groups
        .find((group) => group.name === 'simulated')
        ?.rows.find((item) => item.key === 'share_car');
      for (const [letter, share] of [
        ['A', 0.5],
        ['B', 0.4],
        ['C', 0.3],
      ] as const) {
        Object.assign(row?.values[letter] ?? {}, { value: share });
      }
      Object.assign(row ?? {}, { best: ['C'] });
      await route.fulfill({ json: answer });
    });

    // L-3's primary opens L-4 with every finished version ticked.
    await page.goto(`/#/lab/${built.version}/result/B`);
    await page.reload();
    const main = page.getByRole('main');
    const compare = main.getByRole('button', { name: 'Compare versions →' });
    await expect(compare).toBeVisible();
    await expect(main.getByRole('button', { name: 'Duplicate' })).toBeVisible();
    await compare.click();
    await expect(page).toHaveURL(new RegExp(`#/lab/${built.version}/compare/A,B,C$`));

    // The brief, the picker, the scope, no screen-wide tag, the period chip.
    await expect(main.getByText('Versions of one city instance, side by side')).toBeVisible();
    const picker = main.getByRole('list', { name: 'Versions to compare' });
    await expect(picker.getByRole('button')).toHaveText([
      '✓ A · Baseline',
      '✓ B · Heavier ridership',
      '✓ C · Higher floor',
    ]);
    for (const pill of await picker.getByRole('button').all()) {
      await expect(pill).toHaveAttribute('aria-pressed', 'true');
    }
    await expect(picker.getByText('Flat price 1.00 CHF · simulated · always shown')).toBeVisible();
    await expect(main.getByText(/^Geneva 3 km v1 · .+$/)).toBeVisible();
    await expect(page.getByText(/^Period .+/)).toBeVisible();
    const title = main.getByRole('heading', { level: 2 });
    await expect(title).toHaveText(/^In the simulation, /);

    // The bars: one per column, flat first; the three-mode sentence.
    const bars = main.getByRole('list', { name: 'Simulated split of the travellers' });
    await expect(bars.getByRole('img')).toHaveCount(4);
    await expect(bars.getByRole('img').first()).toHaveAccessibleName(/^Flat price 1\.00 CHF: Car /);
    await expect(main.getByRole('list', { name: 'Modes' }).getByRole('listitem')).toHaveCount(3);
    await expect(main.getByText(THREE_MODES)).toBeVisible();

    // The table: columns, groups with their tags, the caption and the note.
    const table = main.getByTestId('compare-table');
    await expect(table.getByRole('columnheader')).toHaveText([
      'Row',
      'Flat price 1.00 CHF',
      'Version A · Baseline',
      'Version B · Heavier ridership',
      'Version C · Higher floor',
    ]);
    await expect(table.getByTestId('group-head-simulated')).toContainText(
      'SIMULATIONSimulated travellers',
    );
    await expect(table.getByTestId('group-head-model')).toContainText(
      "PRICING MODEL'S RESULTPricing model's result",
    );
    await expect(table.getByTestId('group-head-derived')).toContainText(
      "Computed from the model's flows",
    );
    await expect(table.getByTestId('group-head-goals_that_differ')).toContainText(
      'Pricing goals that differ',
    );
    await expect(table.getByText('Shared bike', { exact: true })).toHaveCount(0);
    await expect(
      main.getByText(
        'Small figures: change against the flat-price column the version is simulated with. The pricing model is not run with a flat price: its rows show — there.',
      ),
    ).toBeVisible();
    await expect(main.getByText('same hubs, routes, travellers and bikes.')).toBeVisible();

    // The flat column shows — outside the simulated group.
    const profit = table.getByTestId('row-simulated-profit').getByRole('cell');
    await expect(profit.first()).not.toHaveText('—');
    const modelRidership = table.getByTestId('row-model-ridership').getByRole('cell');
    await expect(modelRidership.first()).toHaveText('—');

    // The best value of a row has the green ground: C's car share, and neither A's, B's nor the flat one.
    const carCells = table.getByTestId('row-simulated-share_car').getByRole('cell');
    await expect(carCells).toHaveText(['0 %', /^50 %/, /^40 %/, /^30 %/]);
    await expect(carCells.nth(3)).toHaveAttribute('data-best', '');
    for (const at of [0, 1, 2]) {
      await expect(carCells.nth(at)).not.toHaveAttribute('data-best', '');
    }
    await expect(title).toHaveText('In the simulation, Version C has the lowest car share');

    // Where prices differ: the heading, the caption and the map's selector and legend.
    await expect(
      main.getByRole('heading', {
        name: 'Hub pairs where the mean bike price differs most: Version C \u2212 Version B',
      }),
    ).toBeVisible();
    await expect(
      main.getByText(
        "Mean price per bike ride on the pair, weighted by the model's bike rides: a difference mixes a change of price with a change of who rides. Computed from the model's flows.",
      ),
    ).toBeVisible();
    const legend = page.getByRole('group', { name: 'Map legend' });
    await expect(legend).toContainText('Mean bike price: C \u2212 B');
    await expect(legend).toContainText("computed from the model's flows");
    await expect(legend).toContainText('CHF per ride');

    // Unticking a version rewrites the route in place and the columns follow.
    const history = await page.evaluate(() => window.history.length);
    await picker.getByRole('button', { name: '✓ B · Heavier ridership' }).click();
    await expect(page).toHaveURL(new RegExp(`#/lab/${built.version}/compare/A,C$`));
    expect(await page.evaluate(() => window.history.length)).toBe(history);
    await expect(table.getByRole('columnheader')).toHaveText([
      'Row',
      'Flat price 1.00 CHF',
      'Version A · Baseline',
      'Version C · Higher floor',
    ]);
    await expect(main.getByRole('heading', { level: 2 })).not.toContainText('Version B');
    // Two ticked: the ticked pills are disabled.
    await expect(picker.getByRole('button', { name: '✓ A · Baseline' })).toBeDisabled();
    await expect(picker.getByRole('button', { name: '✓ C · Higher floor' })).toBeDisabled();

    // A reload keeps the selection, read from the API alone.
    await page.reload();
    await expect(table.getByRole('columnheader')).toHaveText([
      'Row',
      'Flat price 1.00 CHF',
      'Version A · Baseline',
      'Version C · Higher floor',
    ]);

    // Reticking restores the third column.
    await picker.getByRole('button', { name: 'B · Heavier ridership' }).click();
    await expect(page).toHaveURL(new RegExp(`#/lab/${built.version}/compare/A,B,C$`));
    await expect(table.getByRole('columnheader')).toHaveCount(5);

    // A letter that is not a finished version is an unknown link.
    await page.goto(`/#/lab/${built.version}/compare/A,Z`);
    await expect(
      main.getByText(
        'Nothing at this link: Geneva 3 km v1 has no Version Z. It may have been deleted.',
      ),
    ).toBeVisible();
  });

  test('L-4 · two versions with the same pricing model result say that no hub pair price differs', async ({
    page,
    request,
    control,
  }) => {
    const built = await buildFakeInstance(request, control, SAME_RESULT_DISTANCE_M);
    await finishVersion(request, built.version, 'Baseline');
    await finishVersion(request, built.version, 'Heavier ridership', { ridership_weight: 20 });
    await finishVersion(request, built.version, 'Higher floor', { lowest_price_chf: 0.9 });
    // B's goals with another flat price: the flat price is not read by the solve, so B and D
    // share one stored solve and differ only in the flat column they are simulated against.
    await finishVersion(request, built.version, 'Dearer flat price', {
      ridership_weight: 20,
      flat_price_per_ride_chf: 1.5,
    });

    await page.goto(`/#/lab/${built.version}/compare/B,D`);
    await page.reload();
    const main = page.getByRole('main');

    await expect(
      main.getByText(
        'Versions B and D have the same pricing model result: no hub pair price differs.',
      ),
    ).toBeVisible();
    await expect(main.getByText(/^Hub pairs where the mean bike price differs most/)).toHaveCount(
      0,
    );
    await expect(main.getByRole('heading', { level: 2 })).toHaveText(
      /^Versions B and D have the same prices; against a flat price of 1\.50 instead of 1\.00, their simulated car share is /,
    );
    const table = main.getByTestId('compare-table');
    await expect(table.getByRole('columnheader')).toHaveText([
      'Row',
      'Flat price 1.00 CHF · for B',
      'Version B · Heavier ridership',
      'Flat price 1.50 CHF · for D',
      'Version D · Dearer flat price',
    ]);
    await expect(page.getByLabel('Map shows').getByRole('option')).toHaveText([
      'Mean bike price: D \u2212 B',
      'Mean bike price: D \u2212 flat price',
      'Bike rides starting: D \u2212 B',
    ]);
  });
});
