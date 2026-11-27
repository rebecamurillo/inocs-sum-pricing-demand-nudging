from collections.abc import Sequence

from pricing_demo.domain.errors import DomainError


class InvalidProbeSet(DomainError):
    pass


class ComponentNotControllable(DomainError):
    pass


class BikeStationFetchFailed(DomainError):
    pass


class StreetExtractNotFound(DomainError):
    def __init__(self, found: list[str]) -> None:
        self.found = found
        listing = ", ".join(found) if found else "none"
        super().__init__(
            f"The street extract folder must hold exactly one .osm.pbf file; found: {listing}."
        )


class NoCityDataYet(DomainError):
    def __init__(self) -> None:
        super().__init__("No city data is imported yet: run the city data import first.")


class InvalidTimetable(DomainError):
    pass


class GtfsCopyChanged(DomainError):
    pass


class InvalidStreetExtract(DomainError):
    pass


class BusShapeMatchingFailed(DomainError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class UnknownCityDataset(DomainError):
    def __init__(self, dataset_id: str) -> None:
        self.dataset_id = dataset_id
        super().__init__(f"There is no city data set {dataset_id}.")


class OtherTimetableInGraphFolder(DomainError):
    def __init__(self, names: Sequence[str]) -> None:
        self.names = list(names)
        super().__init__(
            f"The graph folder holds other timetables: {', '.join(self.names)}. "
            "OpenTripPlanner would read them next to gtfs.zip: "
            "the folder must hold only gtfs.zip."
        )


class GraphBuildFailed(DomainError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class PackageDefaultsMissing(DomainError):
    def __init__(self) -> None:
        super().__init__(
            "The runner has not reported the pricing model's package yet: start the worker."
        )


class UnknownStartVersion(DomainError):
    def __init__(self, version_id: str) -> None:
        self.version_id = version_id
        super().__init__(f"There is no instance version {version_id} to start from.")


class VersionNotBuilt(DomainError):
    def __init__(self, version_id: str) -> None:
        self.version_id = version_id
        super().__init__(
            f"The version {version_id} has no stored build: its four steps are not all built."
        )


class SolveNotFound(DomainError):
    def __init__(self, solve_id: str) -> None:
        self.solve_id = solve_id
        super().__init__(f"There is no stored solve {solve_id}.")


class SolveNotVerifiable(DomainError):
    """The stored solve or its simulations cannot be re-run: something they name is missing or
    is a rule the worker cannot build."""

    def __init__(self, solve_id: str, reason: str) -> None:
        self.solve_id = solve_id
        super().__init__(f"The solve {solve_id} cannot be verified: {reason}.")
