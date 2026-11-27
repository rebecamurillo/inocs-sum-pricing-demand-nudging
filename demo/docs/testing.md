# Testing — the dynamic pricing demonstrator

What each kind of test proves, where it lives, when it runs, and how the suite grows.
The rules that bind every change are in `AGENTS.md` (rules 3, 4 and 7).

## Levels

| Level | Proves | Lives in | Runs in | Needs |
| --- | --- | --- | --- | --- |
| Unit | a rule, a calculation, a use case, a component, in isolation with fakes | `api/tests/unit/`, `web/src/**/*.test.ts(x)` | `make check`, `make test` | nothing |
| Contract | a fake and its real adapter behave the same way behind a port | `api/tests/contract/` | the fake, and the real adapters' unreachable cases: `make check`; the rest: `make test-integration` or `make live-smoke` | in `make check`: nothing |
| Architecture | the rules a linter cannot express (which routes exist in which mode, that the API process never loads the package) | `api/tests/architecture/` | `make check` | nothing |
| Integration | repositories, migrations and the worker's claim, lease and cancellation against a real PostgreSQL | `api/tests/integration/` | `make test-integration` | Docker |
| End-to-end | a user's scenario through the browser, the API and the database | `e2e/tests/` | `make e2e` | Docker |
| Live smoke | the real package, solver and trip planner answer | `api/tests/live/` | `make live-smoke` | licence, OpenTripPlanner |

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
  unavailable or, for the solver, limited; a run that fails at a named step; failed route
  queries at named hub pairs). An
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
