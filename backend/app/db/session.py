"""SQLAlchemy engine and the request scoped session dependency."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

engine = create_engine(get_settings().database_url, pool_pre_ping=True, pool_size=20, max_overflow=40)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


@contextmanager
def transaction(db: Session) -> Iterator[Session]:
    """One unit of work. Everything written inside commits together, or none of it does.
    Audit lines are written inside the block, so they commit with the change they describe."""
    try:
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
