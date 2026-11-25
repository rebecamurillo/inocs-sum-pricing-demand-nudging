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
| `tpg_gtfs.zip` | the Geneva public transport timetable (GTFS) | copy of `Geneva_Complete_Link_Instances_and_Optimization/OTP2_Geneva_Instances/tpg_gtfs.zip` in this repository |
| `<name>.osm.pbf` | an OpenStreetMap extract that covers Geneva | download, see below |
| `graph.obj` | the street and transit graph | built by the step below; never copied |

The GTFS file in the repository is a real zip archive (7.5 MB; `trips.txt`, `stop_times.txt`,
`stops.txt` and seven other files), not a Git LFS pointer. OTP finds the files in the folder by
their extensions and names (`.osm.pbf`, a `.zip` with `gtfs` in its name).

OpenStreetMap extract, either of:

- Switzerland, from Geofabrik: <https://download.geofabrik.de/europe/switzerland-latest.osm.pbf>
  (about 500 MB). The Geneva timetable also serves lines that cross into France; for routes on
  that side of the border, add a Geofabrik extract of the Auvergne-Rhone-Alpes region, or build
  one extract that covers both with `osmium`.
- A smaller extract of the Geneva area, drawn on a map at <https://extract.bbbike.org/>
  (format "Protocolbuffer (PBF)").

## Build the graph and start the service

Run from `demo/`:

```sh
cp ../Geneva_Complete_Link_Instances_and_Optimization/OTP2_Geneva_Instances/tpg_gtfs.zip otp/data/
# put the .osm.pbf file in otp/data/ as well
docker compose --profile otp run --rm otp-build   # reads otp/data/, writes otp/data/graph.obj
make up                                           # starts OTP too, because graph.obj exists
```

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
