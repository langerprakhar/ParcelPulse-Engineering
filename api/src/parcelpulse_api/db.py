"""Database engine and session management."""

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def create_db_engine(database_url: str) -> Engine:
    # Connections are opened lazily; pool_pre_ping discards ones the server has closed.
    return create_engine(database_url, pool_pre_ping=True)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def get_session(request: Request) -> Iterator[Session]:
    """FastAPI dependency: one session per request, closed when the request ends."""
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    with session_factory() as session:
        yield session
