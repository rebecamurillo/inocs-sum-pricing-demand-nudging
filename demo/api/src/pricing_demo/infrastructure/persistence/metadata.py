from sqlalchemy import MetaData

# Every constraint and index gets a name derived from its table and columns, so a migration
# can drop or alter it by a name that does not depend on the database's own choice.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# The tables of the application. Alembic compares against it, and the e2e reset empties it.
metadata = MetaData(naming_convention=NAMING_CONVENTION)
