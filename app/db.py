"""Database engine and session management (SQLite via SQLModel)."""

from sqlmodel import Session, SQLModel, create_engine

from app.config import DB_PATH

# check_same_thread=False lets FastAPI's threadpool share the connection pool.
engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
)


def init_db() -> None:
    """Create all tables. Safe to call repeatedly."""
    # Importing models registers them on SQLModel.metadata before create_all.
    from app import models  # noqa: F401

    SQLModel.metadata.create_all(engine)


def get_session():
    """FastAPI dependency yielding a scoped session."""
    with Session(engine) as session:
        yield session
