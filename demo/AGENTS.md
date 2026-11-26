# AGENTS.md — the dynamic pricing demonstrator

The rules, the layout and the commands of everything under `demo/`. The repository root's
[`AGENTS.md`](../AGENTS.md) comes first: the model in `sum_nsm_dynamic_pricing/` is never
edited.

## What this is

A web application that runs the unmodified pricing model for a city and shows its results:
a Python API (`api/`) that calls the package, a static front end (`web/`) that calls the API,
PostgreSQL for storage and OpenTripPlanner for routes. It runs locally.

| Folder | Content | Details |
| --- | --- | --- |
| `api/` | Python 3.13, FastAPI, `uv` | [`docs/architecture.md`](docs/architecture.md) § API |
| `web/` | Astro (static build), React islands, TypeScript, npm | [`docs/architecture.md`](docs/architecture.md) § Web |
| `contracts/` | `openapi.json`, generated from the API | [`docs/api-guidelines.md`](docs/api-guidelines.md) |
| `e2e/` | Playwright scenarios | [`docs/testing.md`](docs/testing.md) |
| `otp/` | OpenTripPlanner service and its local data folder | `otp/README.md` |
| `docs/` | architecture, testing, API guidelines, decisions, notes on the model | — |
| `compose.yaml`, `compose.e2e.yaml` | the local stack and the stack the e2e suite runs against | `README.md` |

## Commands

Run from `demo/`. `make help` lists them.

| Command | What it does | Needs |
| --- | --- | --- |
| `make install` | installs the API (`uv sync`), the web app and the e2e suite (`npm ci`), and the Playwright Chromium browser (`PLAYWRIGHT_ARGS=` skips the browser) | network |
| `make check` | **the quality gate**: format check, lint, types, layer rules, unit and contract tests with coverage, contract freshness, web build, type check, lint and format check of `e2e/` | `make install` |
| `make test` | unit and contract tests of `api/` and `web/` | `make install` |
| `make test-integration` | API tests against a throwaway PostgreSQL, removed afterwards | Docker |
| `make e2e` | builds the e2e stack, runs every Playwright scenario, removes the stack | Docker, `make install` |
| `make contract` | regenerates `contracts/openapi.json` and the web's API types | — |
| `make format` | rewrites files to the formatters' output | — |
| `make dev` | PostgreSQL in Docker (and the trip planner when `otp/data/graph.obj` exists); API (with reload), worker and web on the host | Docker |
| `make worker` | the worker alone on the host, for live runs; Ctrl-C stops it | Docker |
| `make up` / `make down` | the whole local stack in Docker | Docker |
| `make live-smoke` | checks the real package, solver and trip planner | Gurobi licence, running OpenTripPlanner |

A change is finished when `make check` and `make e2e` both exit 0, and `make test-integration`
too when it touches `infrastructure/persistence/`. Report the commands you ran and their
result; if one could not run (no Docker), say so instead of claiming it passed.

## Hard rules

1. **The dependency rule.** Source code dependencies point inwards only:
   `domain` ← `application` ← `infrastructure` and `interface` (API), `domain` ← `application`
   ← `infrastructure` and `presentation` (web). The allowed imports are tables in
   `docs/architecture.md`; `make check` fails on any other import. Fix the design, never the
   linter configuration.
2. **The model sits behind one port.** Only
   `api/src/pricing_demo/infrastructure/pricing_model/` imports `sum_nsm_dynamic_pricing`.
   Model logic is never re-implemented in `demo/`: a number the model produces is read from
   its output; a number the demonstrator derives is computed in `domain/` under a name that
   says so, and both carry their source to the screen.
3. **Tests come with the change.** New behaviour arrives with unit tests of its domain and
   use-case code. A change a user can see adds or updates a Playwright scenario in `e2e/`.
   A bug fix starts with a test that fails for that bug, at the lowest level that reproduces
   it, and with a scenario under `e2e/tests/regressions/` when a user could see it.
4. **Never weaken a test to make it pass.** No `skip`, `xfail`, `only`, `fixme`, loosened
   assertion, raised timeout or lowered coverage threshold. A skipped or focused test fails
   `make check`. A test that is wrong is corrected in its own commit with the reason in the
   message.
5. **The contract is generated, never written.** `contracts/openapi.json` and
   `web/src/infrastructure/api/generated/` come from `make contract`. An API change is made in
   the API, then regenerated; `make check` fails when they are stale.
6. **The database changes only through migrations** in
   `api/src/pricing_demo/infrastructure/persistence/migrations/`. A merged migration is never
   edited; a correction is a new migration.
7. **No test reaches the outside.** Unit, contract and e2e tests use the fake model and the
   fake trip planner; none needs a Gurobi licence, OpenTripPlanner or the internet. Only
   `make live-smoke` does.
8. **Configuration comes from the environment**, read in one place
   (`infrastructure/config/`). `.env.example` documents the values a person sets; the
   Makefile and the Compose files derive the API's `PRICING_DEMO_*` settings from them. No
   secret, licence file or machine path is committed.
9. **Screen text states facts and mechanisms.** It never congratulates, apologises or
   promises. English only.
10. **Stay in scope.** No dependency, folder, service or `make` target is added without a use
    in the same change. No file is created outside `demo/`.

## Architecture in one paragraph

Both applications follow clean architecture with the same four roles. `domain` holds the
entities and rules and knows nothing else. `application` holds one use case per user
intention and declares, as ports, what it needs from the outside. `infrastructure` implements
those ports (database, pricing package, trip planner, HTTP client). The delivery layer
(`interface/http` in the API, `presentation` in the web app) turns requests and clicks into
use-case calls. One composition root per application builds the adapters and injects them.
Read `docs/architecture.md` before adding a file: it says where each kind of code goes.

## Where does this code go?

| You are writing | It goes in |
| --- | --- |
| A rule between values, a calculation on results, an entity | `domain/` |
| Something the user or a client asks the system to do | `application/use_cases/` (one module each) |
| A need for data or a service from outside | a port in `application/ports/`, an adapter in `infrastructure/`, its fake in `infrastructure/fakes/`, a contract test both pass |
| An HTTP route, its request and response shapes | a router factory in `api/.../interface/http/routers/` that takes its use case; one line in `bootstrap.py` mounts it |
| A domain or application error | the error class, and its status and `code` in the one mapping of `interface/http/` (an unmapped error fails `make check`) |
| A table, a query | `api/.../infrastructure/persistence/`, on the shared metadata, and a migration |
| A component, a hook, a style | `web/src/presentation/` |
| A call to the API, a use of browser storage | an adapter in `web/src/infrastructure/` behind a port (`fetch` is refused elsewhere by the lint) |

## Definition of done

- `make check` and `make e2e` exit 0 (and `make test-integration` when persistence changed),
  run by you, results reported.
- The tests required by rule 3 exist and fail without the change.
- Docs that the change makes wrong are corrected in the same change (`README.md`,
  `docs/`, `.env.example`).
- `git status --short ../sum_nsm_dynamic_pricing` prints nothing.

## Conventions

- **Names** say what a thing is in the product's vocabulary: city instance, pricing version,
  pricing goals, result, period, hub, hub pair. The package's parameter names (`P_bar`,
  `theta`) appear only in the pricing-model adapter and in the Advanced view.
- **Errors.** The domain raises typed errors; the delivery layer maps them to responses
  (`docs/api-guidelines.md`). Nothing is caught to be ignored; a failed step reports its name
  and its reason.
- **Python**: type hints everywhere, `mypy --strict` clean, frozen dataclasses in the domain.
  **TypeScript**: `strict`, no `any`, no non-null `!`.
- **Comments** explain why, when the code cannot. No commented-out code.
- **Ports on the host**: API 8100, web 4400, PostgreSQL 5440, OpenTripPlanner 8080; the e2e
  stack uses 14400 and the integration database 5441. All are set in `.env`.
- **Never leave a server running.** Verify through `make check` and `make e2e`, which start
  and remove what they need. If you start `make dev` or `make up`, stop it before you
  finish. Never run `npm run dev` or `astro dev` directly: Astro detaches the server when an
  agent starts it, and it then outlives the session and holds the port.
- **Commits** only when asked: `demo: <what changed>`.
