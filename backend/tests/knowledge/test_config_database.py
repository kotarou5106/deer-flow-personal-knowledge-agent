from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest
from pydantic import ValidationError

from deerflow.knowledge.config import KnowledgeDatabaseConfig
from deerflow.knowledge.database import KnowledgeDatabase, KnowledgeDatabaseNotConfiguredError


def test_database_config_requires_explicit_url_for_initialization() -> None:
    config = KnowledgeDatabaseConfig()
    assert config.database_url is None

    with pytest.raises(KnowledgeDatabaseNotConfiguredError, match="Knowledge database URL is not configured"):
        config.sqlalchemy_url


def test_database_config_masks_password_in_repr() -> None:
    hidden_value = "hidden-value"
    url = "postgresql://" + "user:" + hidden_value + "@example.com/db"
    config = KnowledgeDatabaseConfig(database_url=url)

    assert hidden_value not in repr(config)
    assert hidden_value not in str(config)
    assert config.safe_url == "postgresql://user:***@example.com/db"


def test_database_config_validates_pool_parameters() -> None:
    with pytest.raises(ValidationError):
        KnowledgeDatabaseConfig(database_url="postgresql://localhost/db", pool_size=0)

    with pytest.raises(ValidationError):
        KnowledgeDatabaseConfig(database_url="postgresql://localhost/db", statement_timeout_ms=-1)


def test_database_import_does_not_create_engine() -> None:
    db = KnowledgeDatabase(KnowledgeDatabaseConfig(database_url="postgresql://localhost/db"))
    assert db.engine is None
    assert db.session_factory is None


@pytest.mark.asyncio
async def test_database_initialize_and_dispose_are_explicit() -> None:
    engine = Mock()
    engine.dispose = AsyncMock()
    session_factory = Mock()

    with (
        patch("deerflow.knowledge.database.create_async_engine", return_value=engine) as create_engine,
        patch("deerflow.knowledge.database.async_sessionmaker", return_value=session_factory),
    ):
        hidden_value = "hidden-value"
        url = "postgresql://" + "user:" + hidden_value + "@example.com/db"
        db = KnowledgeDatabase(KnowledgeDatabaseConfig(database_url=url, statement_timeout_ms=5000))
        await db.initialize()

    create_engine.assert_called_once()
    _, kwargs = create_engine.call_args
    assert kwargs["pool_size"] == 5
    assert kwargs["connect_args"]["server_settings"]["statement_timeout"] == "5000"
    assert db.engine is engine
    assert db.session_factory is session_factory

    await db.dispose()
    engine.dispose.assert_called_once()
    assert db.engine is None
    assert db.session_factory is None
