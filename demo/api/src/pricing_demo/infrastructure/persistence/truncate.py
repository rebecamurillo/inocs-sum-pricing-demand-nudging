from sqlalchemy import Engine, MetaData, text


def truncate_all(engine: Engine, metadata: MetaData) -> None:
    """Empty every table of `metadata` in one statement and restart its identity counters.

    Tables outside `metadata` (alembic_version) are left alone.
    """
    if not metadata.tables:
        return
    prepare = engine.dialect.identifier_preparer.format_table
    names = ", ".join(prepare(table) for table in metadata.sorted_tables)
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
