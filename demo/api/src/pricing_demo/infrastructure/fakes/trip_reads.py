from pricing_demo.infrastructure.trip_reads import StoredTripReads


class InMemoryTripReads(StoredTripReads):
    """The traveller view's reads over the in-memory fakes of the stored ports (pass them to
    the constructor); passes the same contract suite as the PostgreSQL adapter."""
