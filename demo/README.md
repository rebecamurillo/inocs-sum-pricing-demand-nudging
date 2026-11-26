# Dynamic pricing demonstrator

A web application that runs the dynamic pricing model of the SUM project (`../sum_nsm_dynamic_pricing`,
used unmodified) for a city and shows its results. A Python API (`api/`) calls the model, a static
front end (`web/`) calls the API, PostgreSQL stores the data and OpenTripPlanner provides routes.

The rules for working in this folder are in [`AGENTS.md`](AGENTS.md); the design, the test strategy
and the API conventions are in [`docs/`](docs/).

## Prerequisites

- Docker with Compose v2
- [uv](https://docs.astral.sh/uv/) (the API's Python 3.13 is installed by uv)
- Node 22 and npm
- GNU Make
- For live runs only: a Gurobi licence and OpenTripPlanner data ([`otp/README.md`](otp/README.md)).
  Tests, `make check` and `make e2e` need neither.

## First-time set-up

```sh
make install     # API (uv sync), web and e2e (npm ci), the Playwright Chromium browser
make check       # the quality gate
make e2e         # the end-to-end scenarios, in Docker
```

To change a port or another per-machine value, copy `.env.example` to `.env` and edit it. Every
variable has a default; the stack starts without a `.env` file.

## Commands

Run from this folder; `make help` lists them.

| Command | What it does |
| --- | --- |
| `make install` | installs the API, the web app, the e2e suite and the Playwright browser |
| `make check` | format, lint, types, layer rules, tests, contract freshness, web build |
| `make test` | unit and contract tests of the API and the web app |
| `make test-integration` | API tests against a throwaway PostgreSQL in Docker |
| `make e2e` | builds the e2e stack, runs the Playwright scenarios, removes the stack |
| `make contract` | regenerates `contracts/openapi.json` and the web API types |
| `make format` | applies ruff format and prettier |
| `make dev` | PostgreSQL in Docker (and OpenTripPlanner when `otp/data/graph.obj` exists); API (with reload), worker and web dev server on the host. Ctrl-C stops those three; the containers keep running until `make down` |
| `make worker` | the worker alone on the host, for live runs; Ctrl-C stops it |
| `make up` / `make down` | the whole stack in Docker / stops it and keeps the database volume |
| `make live-smoke` | checks the real package, solver and trip planner |

`make dev` and `make up` use the same database container and the same host ports; run one at a
time. `make e2e` uses its own project, ports and in-memory database, so it runs beside either.

## URLs

| What | Where |
| --- | --- |
| Web app | <http://localhost:4400> |
| API | <http://localhost:8100/api/v1/system-status>, or `/api/v1/…` through the web app on 4400 |
| API documentation (`make dev`, `make up`) | <http://localhost:8100/api/docs> |
| PostgreSQL | `localhost:5440`, database, user and password `pricing_demo` |
| OpenTripPlanner | <http://localhost:8080> (only when started, see `otp/README.md`) |
| e2e stack (during `make e2e`) | <http://localhost:14400> |

## The Lab

The web app is one page with one React island (`web/src/composition/LabIsland.tsx`). Opening
it lands on `#/lab`; the routes are the hashes `#/lab`, `#/lab/{instance version}`,
`#/lab/{instance version}/pricing/{letter}`, `#/lab/{instance version}/result/{letter}`,
`#/lab/{instance version}/compare/{letters}` and `#/lab/traveller/{instance version}/{letter}`,
each with an optional `?period=`. Any other hash is replaced by `#/lab`.

The footer's wording is set in `web/src/domain/footer.ts`:

- `FUNDING_STATEMENT` is the funding statement.
- `MODEL_AUTHOR` is the name of the model's author. It reads `placeholder` until the
  maintainer supplies the name; then set `MODEL_AUTHOR_IS_PLACEHOLDER` to `false`.
- `RUN_UNMODIFIED_CONFIRMED` is `false`: "Run unmodified." is not shown until the author
  accepts it (question Q-40).

The EU co-funding mark is `web/src/presentation/assets/eu-co-funding-mark-placeholder.svg`.
The maintainer replaces it by `EN-Co-Funded-by-the-EU_POS-1.png` and updates the import in
`web/src/presentation/components/Footer.tsx`.

## Where things are

| Path | Content |
| --- | --- |
| `api/`, `web/` | the two applications |
| `contracts/openapi.json` | the API contract, generated |
| `e2e/` | Playwright scenarios |
| `otp/` | OpenTripPlanner data folder and instructions |
| `compose.yaml`, `compose.e2e.yaml` | the local stack and the stack the e2e suite runs against |
| `.env.example` | every variable the Compose files and the Makefile read |
| `docs/` | architecture, testing, API guidelines, decisions, notes on the model |
