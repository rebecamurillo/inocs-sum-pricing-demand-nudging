# OpenTripPlanner

The pricing model asks OpenTripPlanner (OTP) for routes through its GTFS GraphQL API at
`/otp/gtfs/v1`. `compose.yaml` runs OTP 2.10.0 (`opentripplanner/opentripplanner:2.10.0`) from
the data in `otp/data/`. The API reaches it at `http://otp:8080/otp/gtfs/v1` inside the stack;
the host port is `OTP_PORT` (default 8080).

The data is not in the repository (`otp/data/*` is ignored except `.gitkeep`). Without it,
`make up` does not start OTP and the system status reports the trip planner as unavailable.
Tests and the end-to-end suite never need it.

## What goes in `otp/data/`

| File | Content | Source |
| --- | --- | --- |
| `<name>.osm.pbf` | an OpenStreetMap extract that covers Geneva; exactly one | download, see below |
| `gtfs.zip` | the data set's GTFS copy, with the bus shapes | written by `make otp-graph`; never copied by hand |
| `build-config.json` | the service window, see below | written by `make otp-graph` |
| `graph.obj` | the street and transit graph | built by `make otp-graph`; never copied |
| `graph-manifest.json` | what the graph was built from | written by `make otp-graph` after a successful build |

OTP finds the files in the folder by their extensions and names (`.osm.pbf`, a `.zip` with
`gtfs` in its name). `make otp-graph` therefore refuses to run when another `*gtfs*.zip` (for
example a hand-copied `tpg_gtfs.zip`) is in the folder: OTP would read it next to `gtfs.zip`.
The folder must hold only `gtfs.zip`.

OpenStreetMap extract, either of:

- Switzerland, from Geofabrik: <https://download.geofabrik.de/europe/switzerland-latest.osm.pbf>
  (about 500 MB). The Geneva timetable also serves lines that cross into France; for routes on
  that side of the border, add a Geofabrik extract of the Auvergne-Rhone-Alpes region, or build
  one extract that covers both with `osmium`.
- A smaller extract of the Geneva area, drawn on a map at <https://extract.bbbike.org/>
  (format "Protocolbuffer (PBF)").

## Service window

The Geneva feed is valid from 2024-12-15 to 2025-12-13. OTP 2 by default keeps the services of
a window around the build date (from about one year before it), so a feed whose dates lie in
the past can be dropped entirely and routing on the period's date finds no trip.
`make otp-graph` writes `build-config.json` with the feed's own first and last valid dates:

```json
{"transitServiceStart": "2024-12-15", "transitServiceEnd": "2025-12-13"}
```

Whether routing on the period's date then finds the timetable's trips is checked by the
first graph build on a real machine (M-2).

## Build the graph and start the service

Run from `demo/`:

```sh
# put the .osm.pbf file in otp/data/
make city-data     # imports the timetable (once, or when it changes)
make otp-graph     # DATASET=<id> for a data set other than the latest
make up            # starts OTP too, because graph.obj exists
```

`make otp-graph` copies the data set's GTFS copy to `otp/data/gtfs.zip`, writes
`build-config.json`, runs `docker compose --profile otp run --rm otp-build` (reads `otp/data/`,
writes `graph.obj`) and prints the path of `graph-manifest.json`. A stale manifest is removed
before the build, and a new one is written only when the build succeeded. Its fields:
`otp_image`, `dataset_id`, `gtfs_sha256` (of `gtfs.zip`), `osm_file`, `osm_sha256` and
`build_config`. The worker reads the manifest and hashes `graph.obj` and reports both under
the trip planner's `details` (`graph_manifest`, `graph_sha256`; null without a manifest).
`PRICING_DEMO_OTP_GRAPH_DIR` changes the folder the worker reads (default `otp/data/`);
`make otp-graph` refuses any folder but `otp/data/`, the one the `otp-build` service mounts.

Check that it answers:

```sh
curl -s -X POST http://localhost:8080/otp/gtfs/v1 \
  -H 'Content-Type: application/json' -d '{"query":"{ __typename }"}'
```

`make live-smoke` then checks the trip planner together with the package and the solver.

## Memory

The Java heap is `OTP_HEAP` in `.env` (default `8g`), passed to the container as
`JAVA_TOOL_OPTIONS=-Xmx<OTP_HEAP>`, which the JVM reads whatever the image's start script does.
Building a graph from a country-sized extract needs the most; serving a built graph needs less.
Docker must be allowed more memory than the heap (Docker Desktop: Settings, Resources). A
smaller extract allows a smaller heap.

## Command-line options of the 2.10.0 image

The image's entry point runs OTP on `/var/opentripplanner/` (the mounted `otp/data/`) and
appends the command given to the container (`docker run <image> --help` lists the options):

| Service | Command | Meaning |
| --- | --- | --- |
| `otp-build` | `--build --save` | build the graph from the inputs and write `graph.obj` |
| `otp` | `--load --serve` | read `graph.obj` and answer requests; the image's help says `--load` implies `--serve`, which is written out so the command reads as what it does |

## What has not been run on this set-up

- No OpenStreetMap extract was downloaded, no graph was built and OTP was not started. Nothing
  in this file was run end to end.
- Verified: the image tag `opentripplanner/opentripplanner:2.10.0` exists
  (`docker manifest inspect`), `docker compose --profile otp config` resolves both services,
  and `tpg_gtfs.zip` is a real zip.
- Verified against the pinned image (`docker run`, no data): `--help` lists `--build`,
  `--save`, `--load` and `--serve` as used above, and the heap follows
  `JAVA_TOOL_OPTIONS=-Xmx300m` (`MaxHeapSize` printed by the JVM).
- Not verified: that OTP 2.10.0 builds a graph from this GTFS file, the memory the build
  needs, and that the service answers once a graph is loaded.
