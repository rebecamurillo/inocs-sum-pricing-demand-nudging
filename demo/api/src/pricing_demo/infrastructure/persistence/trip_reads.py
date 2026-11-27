from sqlalchemy import Engine

from pricing_demo.infrastructure.persistence.artifacts import PostgresArtifacts
from pricing_demo.infrastructure.persistence.city_datasets import PostgresCityDatasets
from pricing_demo.infrastructure.persistence.city_instances import PostgresCityInstances
from pricing_demo.infrastructure.persistence.read_model import PostgresReadModel
from pricing_demo.infrastructure.persistence.route_failures import PostgresRouteFailures
from pricing_demo.infrastructure.trip_reads import StoredTripReads


class PostgresTripReads(StoredTripReads):
    """The traveller view's reads on the PostgreSQL adapters of the stored ports."""

    def __init__(self, engine: Engine) -> None:
        super().__init__(
            PostgresCityInstances(engine),
            PostgresCityDatasets(engine),
            PostgresArtifacts(engine),
            PostgresReadModel(engine),
            PostgresRouteFailures(engine),
        )
