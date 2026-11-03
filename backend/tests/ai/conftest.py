"""Shared fixtures. Database tests run in a throwaway schema of the container Postgres."""

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@pytest.fixture(scope="session")
def engine(test_database: str, owner_engine) -> Iterator:
    """The limited app role on the migrated test database, so the real tables and grants are used."""
    eng = create_engine(get_settings().database_url)
    yield eng
    eng.dispose()


@pytest.fixture
def session_factory(engine, owner_engine) -> sessionmaker[Session]:
    with owner_engine.begin() as conn:
        conn.execute(text("TRUNCATE prompt_runs, prompt_versions, prompts RESTART IDENTITY CASCADE"))
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def pytest_configure(config) -> None:
    config.addinivalue_line("markers", "live: calls the real Claude API. Needs RUN_LIVE_AI=1 and a key")
