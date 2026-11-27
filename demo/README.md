# Dynamic pricing demonstrator

A web application that runs the dynamic pricing model of the SUM project (`../sum_nsm_dynamic_pricing`,
used unmodified) for a city and shows its results. A Python API (`api/`) calls the model, a static
front end (`web/`) calls the API, PostgreSQL stores the data and OpenTripPlanner provides routes.

The rules for working in this folder are in [`AGENTS.md`](AGENTS.md); the design, the test strategy
and the API conventions are in [`docs/`](docs/).

## Test-only set-up

`make check`, `make e2e` and every test use the fake model and the fake trip planner. They need
Docker with Compose v2, [uv](https://docs.astral.sh/uv/), Node 22, npm and GNU Make, and
neither a Gurobi licence nor OpenTripPlanner nor the internet:

```sh
make install     # API (uv sync), web and e2e (npm ci), the Playwright Chromium browser
make check       # the quality gate
make e2e         # the end-to-end scenarios, in Docker
```

## Live set-up

The steps that take an empty machine to a built Geneva instance, in order. `verify-build` and
the live set-up are maintainer commands: neither `make check` nor `make e2e` runs them.

1. **The Gurobi licence and Python.** The model's solver needs a Gurobi licence on the host
   (see `docs/architecture.md`, the worker set-up). Python 3.13 comes through uv: nothing to
   install by hand. The OpenTripPlanner data is described in [`otp/README.md`](otp/README.md):
   put the one `.osm.pbf` extract of the area in `otp/data/`.
2. **`make install`**: the API (`uv sync`), the web app and the e2e suite (`npm ci`), the
   Playwright Chromium browser.
3. **`make city-data`**: imports the Geneva timetable and the first bike-station snapshot as a
   data set `geneva-{date}` in the database and `var/data/datasets/` (needs the internet for
   the bike stations). The import runs pfaedle in Docker to draw the bus legs on the streets of
   that extract; without Docker, or when pfaedle produces no bus shape, the import still
   succeeds, the data set records `bus_shapes = none` with the reason, and bus legs stay
   straight lines between stops.
4. **The bike-feed refresh**, whenever a newer station snapshot is wanted (it makes a new data
   set with the latest timetable and the new stations):

   ```sh
   uv --directory api run pricing-demo-worker refresh-bike-stations
   ```

5. **`make otp-graph`**: OpenTripPlanner's graph from the latest data set, in `otp/data/`
   (`DATASET=<id>` for another; see [`otp/README.md`](otp/README.md)).
6. **`make basemap`**: the map's background `web/public/basemap/{dataset}.pmtiles` from the same
   `.osm.pbf`.
7. **`make dev`**, or `make up` then `make worker`: the stack with the real adapters
   (`ADAPTERS=real`, the default; see `.env.example`). Open the web app and build an instance
   version in the Lab.
8. **`make live-smoke`**: checks the real package, solver and trip planner: the licence is
   `available` (`test_the_solver_probe_answers`) and a 500 m instance solves end to end under a
   full licence (`api/tests/live/test_real_pricing_model.py`). Both are the maintainer's, with a
   full Gurobi licence and a running trip planner; so is a real pricing model run on a city
   instance, which is never an unattended test. `make test-model` solves a tiny committed
   instance with the size-limited licence of the PyPI `gurobipy`, without a licence file.

## Measurements

The measurement procedure is M-1 to M-3 of `ARCHITECTURE.md` § 12 (in the project folder,
`initiatives/dynamic-pricing-demonstrator/`). M-1 to M-6 are a maintainer follow-up after
delivery (`ARCHITECTURE.md` § 12, Q-10 closed for this version).

- **M-1**: `make live-smoke`, then read `/api/v1/system-status`: the licence is `available` on
  the host.
- **M-2**: import the Geneva data set with the bus shapes, run `make otp-graph`; record the
  build time, the peak memory (`docker stats`) and the graph size.
- **M-3**: in the Lab build Geneva instances of radius 1, 2 and 3 km with the defaults, then
  rebuild 3 km with `PRICING_DEMO_OTP_WORKERS` 1, 4 and 8 with reuse off. Read each step's
  duration, its pair counts and `failure_pct` from `/api/v1/runs/{id}`, and the failed queries
  from `/api/v1/runs/{id}/route-failures`.

To show that a build is reproducible, rebuild an instance version from scratch and compare it
with the stored one:

```sh
uv --directory api run pricing-demo-worker verify-build geneva-3km.v1
```

It runs steps 1 to 4 with reuse off in `var/data/verify/{uuid}/` (deleted at the end), writes
nothing to the database, prints one line per step (`match` or `differ`, with the stored and the
rebuilt sha256 of each file) and a last line `verify-build {version}: match` or `: differ`.
When a trip-planner query failed in either build, the routes and travellers steps compare the
hub pairs both builds have and list the others. Exit status: 0 when everything compared
matches, 1 when something differs, 2 when the version is unknown or not built, or a rebuild
step fails (the reason is on stderr).

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
| `make city-data` | imports the Geneva timetable, the bus legs drawn on the streets and the first bike-station snapshot as a city data set |
| `make otp-graph` | builds OpenTripPlanner's graph from the latest city data set (`DATASET=<id>` for another): copies its timetable to `otp/data/gtfs.zip`, sets the service window, runs the build in Docker and writes `otp/data/graph-manifest.json` |
| `make basemap` | builds the map's background `web/public/basemap/{dataset}.pmtiles` (git-ignored) from the `.osm.pbf` in `otp/data/` with Planetiler in Docker, clipped to the latest data set's available area (`DATASET=<id>` for another); without it the map is the ground colour |
| `make up` / `make down` | the whole stack in Docker / stops it and keeps the database volume |
| `make live-smoke` | checks the real package, solver and trip planner: the licence is `available` and a 500 m instance solves end to end (the maintainer's, with a full licence) |
| `uv --directory api run pricing-demo-worker verify-build {instance version}` | rebuilds steps 1-4 of a built version with reuse off in a scratch folder and compares the file hashes with the stored build; exit 0 only when they match |

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

- `FUNDING_STATEMENT` is the funding statement. Its source is the sentence that accompanies
  the EU co-funding mark in the team folder (`knowledge/visual-identity.md` § Sources).
- `MODEL_AUTHOR` is the model author's name in "Pricing model: {model author}, Inria INOCS.".
  It reads `placeholder` until the maintainer supplies the name; then set
  `MODEL_AUTHOR_IS_PLACEHOLDER` to `false`.
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
