# Testing — the dynamic pricing demonstrator

What each kind of test proves, where it lives, when it runs, and how the suite grows.
The rules that bind every change are in `AGENTS.md` (rules 3, 4 and 7).

## Levels

| Level | Proves | Lives in | Runs in | Needs |
| --- | --- | --- | --- | --- |
| Unit | a rule, a calculation, a use case, a component, in isolation with fakes | `api/tests/unit/`, `web/src/**/*.test.ts(x)` | `make check`, `make test` | nothing |
| Contract | a fake and its real adapter behave the same way behind a port | `api/tests/contract/` | the fake, and the real adapters' unreachable cases: `make check`; the rest: `make test-integration` or `make live-smoke` | in `make check`: nothing |
| Architecture | the rules a linter cannot express (which routes exist in which mode, that the API process never loads the package) | `api/tests/architecture/` | `make check` | nothing |
| Characterisation | what the unmodified package writes and the adapter depends on: the files and fields of the four steps, the routes step's log templates, retries, dropped pairs and sorted file against a local trip-planner stub, integer demand, the sign of `delta_ia`, the bike-leg count, the Geneva stop, station and hub counts; step 5 on a tiny committed instance under the size-limited licence of the PyPI `gurobipy` (test 5: pinned rows, identical rows on a second solve, a `PT+Bike` row only for an offered option, the four objective terms adding up to the objective), the twelve choice-model coefficients found in the installed solver (test 6), and the real `PricingSolver` passing the contract suite | `api/tests/characterisation/` | `make test-model`; the CI job `model` | the package's dependencies; no licence, trip planner or internet |
| Integration | repositories, migrations and the worker's claim, lease and cancellation against a real PostgreSQL | `api/tests/integration/` | `make test-integration` | Docker |
| End-to-end | a user's scenario through the browser, the API and the database | `e2e/tests/` | `make e2e` | Docker |
| Live smoke | the real package, solver and trip planner answer; OpenTripPlanner answers a Monday (2025-03-10, arrive by 08:30) query with a transit leg, its graph was built from the latest data set's timetable, a 500 m instance builds steps 1 to 4 on the real adapters, the licence is `available`, and a 500 m instance solves end to end under a full licence | `api/tests/live/` | `make live-smoke` | licence, OpenTripPlanner |

Most tests are unit tests: the domain and the use cases hold the behaviour and need no
set-up. End-to-end tests are few and each covers one thing a user does.

## Unit tests

- Test behaviour through the public function or the use case's `execute()`, not private
  helpers.
- A use case is tested with fakes of its ports, never with mocks that assert call order.
- One reason to fail per test; the name states the behaviour:
  `test_runs_are_blocked_when_the_trip_planner_is_unavailable`.
- Coverage of the `domain` and `application` code stays at or above 90 % in both
  applications; `make check` enforces it. The threshold is never lowered.
- A skipped, expected-to-fail, focused or disabled test fails `make check` in all three
  suites.

## Contract tests

Each port has one suite, written against the port. It is run once per implementation
through a parametrised fixture: always against the fake; against the real adapters in the
situations that need no outside service (an unreachable database URL, a closed local port)
in `make check`; and under the `integration` marker (a working PostgreSQL) or the `live`
marker (package, solver, running trip planner) otherwise.
The suite asserts behaviour, not types: each implementation supplies the situations the
port's contract names (for a probe: the component working, unavailable, and for the solver
limited) and the same assertions run on all of them. The report store (`ComponentReports`) and
the fake settings store each have their suite (`contract/test_component_reports.py`,
`contract/test_fake_settings.py`): in memory always, PostgreSQL under `integration`. A fake that drifts from the real adapter fails
here. Adding a port means adding its fake and its suite in the same change.

## Characterisation tests

They run the unmodified package, through the real `CityPreparation` and its child process, on
committed fixtures: a synthetic GTFS feed, a GBFS file and a routes file under
`api/tests/characterisation/fixtures/` (inside `demo/`, so `demo/.gitattributes` keeps them out
of Git LFS), and the Geneva feed of `Geneva_Complete_Link_Instances_and_Optimization/` read in
place. They carry the marker `characterisation`: `make check` collects them and runs none
(`not integration and not live and not characterisation`); `make test-model` runs them, locally
and in the CI job `model`.

They pin what the demonstrator depends on, so that a change of the package that breaks it fails
here (ARCHITECTURE.md § 11.2): tests 1 to 4 and 8 (the files and fields of steps 1, 2 and 4; the
bike-leg count; integer demand; the sign of `delta_ia`: -1 where a bike is taken; for the routes
step, the log templates, the retry policy, the dropped itineraries and pairs, the repeated option
ids of a resumed build and the sort). The routes tests (`test_routes.py`) run against a local
OpenTripPlanner stub (`otp_stub.py`: an HTTP server in the test process answering the committed
`fixtures/otp_answers.json`, with scripted failures and recorded requests); the facts that need a
fresh interpreter (the resumed build, one seed on two orders of the same pairs) run the package
in a subprocess, the pytest process never imports it. The golden numbers (the stop, bike-station and hub counts of the
Geneva feed at 500 m) are fixed at the first run and change only with a change of the package or
the feed, the reason in the commit. The real `CityPreparation` joins the port's contract suite
under this marker (the `port` fixture of `contract/test_city_preparation.py`).

## Integration tests

They run against the database named by `PRICING_DEMO_TEST_DATABASE_URL` and refuse to run
without it: they drop and recreate the schema, so they never use the application's
database. `make test-integration` starts a throwaway PostgreSQL, sets the variable and
removes the container afterwards.

The worker's integration tests (`test_worker_claim.py`, `test_worker_lease.py`,
`test_worker_cancellation.py`, `test_worker_recovery.py`) run the real repository and registry
with a fixed clock and a fake waiter, so the 1 s poll, the 5 s heartbeat, the 2 s cancellation
check, the 10 s recovery pass and the 60 s lease are driven by the test and never slept. Concurrency is tested with threads and a barrier.

## End-to-end tests

```
e2e/
  package.json  playwright.config.ts
  tests/
    <capability>.spec.ts        one file per capability (system-status, city-instance, …)
    regressions/                one scenario per fixed bug that a user could see
  support/                      the fixtures every test uses, the client of the test-control API, page objects
```

- **One worker.** What the fakes answer is one shared row in the database, so scenarios run
  one after the other.

- **The stack.** `compose.e2e.yaml` starts PostgreSQL, the API with the fake adapters, the
  worker with the fake adapters and the web container, on its own project name and port (14400), so it runs beside `make dev`.
  `make e2e` builds it, waits for it, runs Playwright from the host and removes it. It exports
  `E2E_COMPOSE` (the compose command with an absolute file path) to the run, which
  `e2e/support/stack.ts` uses to restart the `api` and `worker` services.
- **A scenario** is written from what the user does and reads, and its title carries the
  requirement or screen it covers: `test('L-1 · saving an edited instance creates a new
  version', …)`.
- **Selectors** are roles, labels and visible text. No CSS selector, no test id unless the
  element has no accessible name, no fixed wait.
- **State.** Every test starts from an empty database and from fakes in their default
  state: a fixture calls the test-control reset before each test and waits for the status to read
  every component available again. The reset truncates every
  table of the application's metadata, so a new table is covered without further work.
  Tests do not depend on each other's order.
- **The test-control API** (`/api/test-control/…`) exists only when the API runs with the
  fake adapters. It resets stored data and sets what the fakes answer (a component
  unavailable or, for the solver, limited; a run that fails at a named step, a build step or
  `pricing_model` (`fail_at`; `hold_at` holds a build step only); the licence kind the fake
  solver records on its solves (`licence_kind`, `full` unless a test sets `limited`); the
  traveller simulation rule the worker uses (`simulation_rule`: `version`, `price_weight`,
  `time_weight`, `balanced-score` v1 with 0.5 and 0.5 unless a test stages another; the version
  is at least 2, because a staged version 1 with other weights would replace the links of the
  version 1 simulations and leave them unlinked, and the worker records it on its next
  heartbeat, so a scenario waits for `/system-status` to show it); failed
  route queries at named hub pairs). An
  architecture test asserts it is not mounted with the real adapters. It is the only test
  seam: a scenario never stubs the network in the browser.
- **Fakes are set through `fake_settings`.** The API and the worker are two processes, so the
  test-control routes write one row of the table `fake_settings` and the worker's fake probes
  read it at each report cycle. The worker reports the components every second on the e2e
  stack (`PRICING_DEMO_COMPONENT_REPORT_INTERVAL_S: 1`) and the reset truncates every table
  and writes the default settings (every component available). `TestControl.reset()` and
  `setComponent()` therefore wait, with a polling assertion on `GET /api/v1/system-status`,
  until the status shows the change: a scenario never sleeps. With real adapters
  `fake_settings` stays empty and nothing constructs its store (an architecture test).
- **When a scenario fails**, the stack's logs are in `e2e/test-results/stack.log` and the
  Playwright report in `e2e/playwright-report/`.

## How the suite grows

| Change | Tests it brings |
| --- | --- |
| A new rule or calculation | unit tests of the domain code |
| A new use case | unit tests with fakes; a route test of its HTTP mapping |
| A new port | a fake, a contract suite, the real adapter under its marker |
| A new or changed screen behaviour | a component test; an e2e scenario added or updated |
| A changed API shape | regenerated contract; the adapters' tests updated |
| A bug fix | first a failing test at the lowest level that reproduces it; when a user could see the bug, also `e2e/tests/regressions/<short-name>.spec.ts`, with one comment line stating what was wrong |

A scenario that fails after a change is information: the behaviour changed. Either the
change is wrong, or the requirement changed and the scenario is updated in the same change,
with the reason in the commit message. It is never skipped.

## What tests never do

Call the internet, need a licence, sleep for a fixed time, depend on the clock or on random
numbers without a seed, or leave data behind.
