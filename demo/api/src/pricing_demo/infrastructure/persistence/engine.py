from sqlalchemy import Engine, create_engine

CONNECT_TIMEOUT_S = 2


def create_db_engine(database_url: str) -> Engine:
    """Build the engine without connecting: the first query opens the first connection.

    A pooled connection that the server closed meanwhile (a restart, an idle timeout) is
    detected and replaced before use, so a restarted database does not fail the next request.
    """
    return create_engine(
        database_url,
        connect_args={"connect_timeout": CONNECT_TIMEOUT_S},
        pool_pre_ping=True,
    )
