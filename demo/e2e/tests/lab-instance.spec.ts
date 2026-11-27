import { buildFakeInstance } from '../support/build';
import { expect, test } from '../support/fixtures';

interface RoutesAnswer {
  queries: number;
  queries_failed: number;
  failure_pct: number;
  pairs_without_public_transport: number;
  pairs_without_car: number;
  retries: number;
}

interface VersionAnswer {
  routes: RoutesAnswer | null;
}

function present<T>(value: T | null): T {
  expect(value).not.toBeNull();
  return value as T;
}

// Not the 900 m of the other scenarios: artefacts outlive a reset and are keyed by parameters.
const FAILING_BUILD_DISTANCE_M = 950;

const grouped = (n: number) => String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
const plural = (n: number, one: string, many: string) => (n === 1 ? one : many);

test.describe('Lab', () => {
  test('L-1 · some route queries fail: the build is stored, the routes step shows the failure rate, and the pairs without a route are listed', async ({
    page,
    request,
    control,
  }) => {
    // Both queries and both kinds, on pairs the fake city requests.
    await control.setPricingModel({
      route_failures: [
        {
          origin_hub: 'H1',
          destination_hub: 'H6',
          query: 'pt_bike',
          kind: 'technical',
          message: 'trip planner timeout',
        },
        {
          origin_hub: 'H2',
          destination_hub: 'H6',
          query: 'pt_bike',
          kind: 'no_route',
          message: 'no public transport route',
        },
        {
          origin_hub: 'H1',
          destination_hub: 'H2',
          query: 'car',
          kind: 'no_route',
          message: 'no car route',
        },
        {
          origin_hub: 'H6',
          destination_hub: 'H1',
          query: 'car',
          kind: 'technical',
          message: 'trip planner timeout',
        },
      ],
    });
    const { version } = await buildFakeInstance(request, control, FAILING_BUILD_DISTANCE_M);
    const answer = (await (
      await request.get(`/api/v1/instance-versions/${version}`)
    ).json()) as VersionAnswer;
    const routes = present(answer.routes);
    expect(routes.queries_failed).toBe(4);
    const hubs = (await (
      await request.get(`/api/v1/instance-versions/${version}/hubs`)
    ).json()) as {
      items: { hub_id: string; label: string }[];
    };
    const label = (id: string) => hubs.items.find((hub) => hub.hub_id === id)?.label ?? id;

    await page.goto(`/#/lab/${version}`);

    // The saved card: the brief, the ready line, the five counts and the edit action.
    await expect(page.getByText('City instance · pipeline steps 1 to 4')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Geneva 3 km' })).toBeVisible();
    await expect(
      page.getByText(/^Ready · saved \d{1,2} [A-Z][a-z]{2} \d{4} · used by 0 pricing versions$/),
    ).toBeVisible();
    for (const countLabel of [
      'Stops and platforms',
      'Bike stations',
      'Hubs',
      'Hub pairs with routes',
      'Travellers in the period',
    ]) {
      await expect(
        page.getByRole('term').filter({ hasText: new RegExp(`^${countLabel}$`) }),
      ).toBeVisible();
    }
    await expect(page.getByRole('button', { name: 'Edit as a new version' })).toBeVisible();
    // The data set's own name, written once.
    await expect(
      page.getByRole('definition').filter({ hasText: /^Geneva · tpg \+ Donkey Republic$/ }),
    ).toBeVisible();
    await expect(page.getByLabel('Breadcrumb')).toHaveText('Geneva 3 km v1 › Instance set-up');
    await expect(page.getByText('Period Monday 08:00–09:00')).toBeVisible();

    // The Routes line, from the version's own numbers.
    const pct = routes.failure_pct.toFixed(1);
    const a = routes.pairs_without_public_transport;
    const b = routes.pairs_without_car;
    const line =
      `Routes: ${grouped(routes.queries_failed)} of ${grouped(routes.queries)} trip-planner queries gave no route (${pct} %). ` +
      `${grouped(a)} ${plural(a, 'hub pair has', 'hub pairs have')} no public transport route and ${plural(a, 'is', 'are')} not priced; ` +
      `${plural(b, '1 has', `${grouped(b)} have`)} no car option. ` +
      `A technical error is tried ${String(routes.retries)} times before it counts.`;
    await expect(page.getByText(line)).toBeVisible();

    // The table of the failures.
    await page
      .getByRole('button', {
        name: `Show the ${grouped(routes.queries_failed)} hub pairs without a route`,
      })
      .click();
    const table = page.getByRole('table');
    await expect(table.getByRole('columnheader')).toHaveText([
      'From → to',
      'Query',
      'What happened',
      'Effect',
      'Show on map',
    ]);
    const tries = `Trip planner error after ${String(routes.retries)} tries: trip planner timeout`;
    const expectedRows = [
      [`${label('H1')} → ${label('H2')}`, 'Car', 'No route found', 'No car option'],
      [
        `${label('H1')} → ${label('H6')}`,
        'Public transport',
        tries,
        'Not in the instance: not priced',
      ],
      [
        `${label('H2')} → ${label('H6')}`,
        'Public transport',
        'No route found',
        'Not in the instance: not priced',
      ],
      [`${label('H6')} → ${label('H1')}`, 'Car', tries, 'No car option'],
    ];
    const rows = table.getByRole('row');
    await expect(rows).toHaveCount(expectedRows.length + 1);
    for (const [at, expected] of expectedRows.entries()) {
      // The last cell holds the "Show on map" button.
      await expect(rows.nth(at + 1).getByRole('cell')).toHaveText([...expected, 'Show on map']);
    }

    // "Show on map" adds the legend entry.
    await expect(page.getByText('Hub pair without a route')).toHaveCount(0);
    await rows.nth(1).getByRole('button', { name: 'Show on map' }).click();
    await expect(page.getByRole('list', { name: 'Map legend' })).toContainText(
      'Hub pair without a route',
    );
  });
});
