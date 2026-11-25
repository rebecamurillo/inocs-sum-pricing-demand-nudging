from typing import Any

from sqlalchemy import Column, ForeignKey, Integer, MetaData, String, Table, create_mock_engine
from sqlalchemy.engine.mock import MockConnection

from pricing_demo.infrastructure.persistence.metadata import NAMING_CONVENTION, metadata


def ddl_of(local: MetaData) -> str:
    """The PostgreSQL statements that create every table of `local`, without a database."""
    statements: list[str] = []

    def record(statement: Any, *_: Any, **__: Any) -> None:
        statements.append(str(statement.compile(dialect=engine.dialect)))

    engine: MockConnection = create_mock_engine("postgresql+psycopg://", record)
    local.create_all(engine, checkfirst=False)
    return "\n".join(statements)


def test_the_application_metadata_names_its_constraints_by_convention() -> None:
    assert metadata.naming_convention == NAMING_CONVENTION


def test_every_kind_of_constraint_and_index_gets_a_derived_name() -> None:
    local = MetaData(naming_convention=NAMING_CONVENTION)
    Table("owner", local, Column("id", Integer, primary_key=True))
    Table(
        "pet",
        local,
        Column("id", Integer, primary_key=True),
        Column("name", String, unique=True),
        Column("owner_id", Integer, ForeignKey("owner.id")),
        Column("age", Integer, index=True),
    )

    ddl = ddl_of(local)

    assert "CONSTRAINT pk_owner PRIMARY KEY (id)" in ddl
    assert "CONSTRAINT pk_pet PRIMARY KEY (id)" in ddl
    assert "CONSTRAINT uq_pet_name UNIQUE (name)" in ddl
    assert "CONSTRAINT fk_pet_owner_id_owner FOREIGN KEY(owner_id) REFERENCES owner (id)" in ddl
    assert "CREATE INDEX ix_pet_age ON pet (age)" in ddl
