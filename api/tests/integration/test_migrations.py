"""Migration sanity: the schema builds from zero, matches the models, and is reversible."""

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, inspect

from parcelpulse_api.models import Base
from tests.integration.conftest import alembic_config


def test_upgrade_from_empty_database_creates_every_model_table(migrated_engine: Engine) -> None:
    tables = set(inspect(migrated_engine).get_table_names())
    assert set(Base.metadata.tables) <= tables
    assert "alembic_version" in tables


def test_database_is_at_the_single_head_revision(
    migrated_engine: Engine, database_url: str
) -> None:
    heads = ScriptDirectory.from_config(alembic_config(database_url)).get_heads()
    assert len(heads) == 1, f"migration history has diverged: {heads}"
    with migrated_engine.connect() as connection:
        assert MigrationContext.configure(connection).get_current_revision() == heads[0]


def test_models_and_migrations_do_not_drift(migrated_engine: Engine) -> None:
    with migrated_engine.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    assert diff == [], f"models differ from the migrated schema: {diff}"


def test_downgrade_to_base_and_upgrade_again(migrated_engine: Engine, database_url: str) -> None:
    config = alembic_config(database_url)

    command.downgrade(config, "base")
    assert set(inspect(migrated_engine).get_table_names()) == {"alembic_version"}

    command.upgrade(config, "head")
    assert set(Base.metadata.tables) <= set(inspect(migrated_engine).get_table_names())
