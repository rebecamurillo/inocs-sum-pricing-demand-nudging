from collections.abc import Collection, Sequence

from sqlalchemy import Engine, func, select

from pricing_demo.domain.city_datasets import (
    BoundingBox,
    CityDataset,
    GbfsSnapshot,
    GtfsSnapshot,
    Preset,
    RoutingMoment,
)
from pricing_demo.infrastructure.persistence.tables import city_datasets


def _polygon_box(polygon: dict[str, object]) -> BoundingBox:
    ring = polygon["coordinates"][0]  # type: ignore[index]
    lons = [point[0] for point in ring]
    lats = [point[1] for point in ring]
    return BoundingBox(min(lons), min(lats), max(lons), max(lats))


class PostgresCityDatasets:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def add(self, dataset: CityDataset) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                city_datasets.insert().values(
                    id=dataset.id,
                    name=dataset.name,
                    gtfs_file=dataset.gtfs.file,
                    gtfs_sha256=dataset.gtfs.sha256,
                    gtfs_source_sha256=dataset.gtfs.source_sha256,
                    gtfs_valid_from=dataset.gtfs.valid_from,
                    gtfs_valid_to=dataset.gtfs.valid_to,
                    gtfs_timezone=dataset.gtfs.timezone,
                    gbfs_file=dataset.gbfs.file,
                    gbfs_sha256=dataset.gbfs.sha256,
                    gbfs_source_url=dataset.gbfs.source_url,
                    gbfs_fetched_at=dataset.gbfs.fetched_at,
                    available_area=dataset.available_area.to_geojson_polygon(),
                    preset={
                        "centre_lat": dataset.preset.centre_lat,
                        "centre_lon": dataset.preset.centre_lon,
                        "radius_m": dataset.preset.radius_m,
                    },
                    routing_date=dataset.routing_moment.date,
                    routing_time=dataset.routing_moment.time,
                    arrive_by=dataset.routing_moment.arrive_by,
                    routing_date_provisional=dataset.routing_moment.provisional,
                    created_at=dataset.created_at,
                )
            )

    def list(self) -> Sequence[CityDataset]:
        query = select(city_datasets).order_by(city_datasets.c.created_at, city_datasets.c.id)
        with self._engine.connect() as connection:
            return [self._dataset(row) for row in connection.execute(query)]

    def latest(self) -> CityDataset | None:
        query = (
            select(city_datasets)
            .order_by(city_datasets.c.created_at.desc(), city_datasets.c.id.desc())
            .limit(1)
        )
        with self._engine.connect() as connection:
            row = connection.execute(query).first()
        return self._dataset(row) if row else None

    def ids_starting_with(self, prefix: str) -> Collection[str]:
        escaped = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = select(city_datasets.c.id).where(
            city_datasets.c.id.like(escaped + "%", escape="\\")
        )
        with self._engine.connect() as connection:
            return {row.id for row in connection.execute(query)}

    def count(self) -> int:
        with self._engine.connect() as connection:
            return connection.execute(select(func.count()).select_from(city_datasets)).scalar_one()

    @staticmethod
    def _dataset(row) -> CityDataset:  # type: ignore[no-untyped-def]
        return CityDataset(
            id=row.id,
            name=row.name,
            gtfs=GtfsSnapshot(
                file=row.gtfs_file,
                sha256=row.gtfs_sha256,
                source_sha256=row.gtfs_source_sha256,
                valid_from=row.gtfs_valid_from,
                valid_to=row.gtfs_valid_to,
                timezone=row.gtfs_timezone,
            ),
            gbfs=GbfsSnapshot(
                file=row.gbfs_file,
                sha256=row.gbfs_sha256,
                source_url=row.gbfs_source_url,
                fetched_at=row.gbfs_fetched_at,
            ),
            available_area=_polygon_box(row.available_area),
            preset=Preset(
                centre_lat=row.preset["centre_lat"],
                centre_lon=row.preset["centre_lon"],
                radius_m=row.preset["radius_m"],
            ),
            routing_moment=RoutingMoment(
                date=row.routing_date,
                time=row.routing_time,
                arrive_by=row.arrive_by,
                provisional=row.routing_date_provisional,
            ),
            created_at=row.created_at,
        )
