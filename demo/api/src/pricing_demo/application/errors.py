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
