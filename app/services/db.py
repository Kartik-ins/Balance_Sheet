"""
Database Connection Manager
===========================
Handles database connections, sessions, and initialization.
"""
from contextlib import contextmanager, asynccontextmanager
from typing import Generator, AsyncGenerator
from pathlib import Path
import structlog

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from app.config import get_settings
from app.models.database import Base

logger = structlog.get_logger()
settings = get_settings()


# Convert async URL to sync for SQLite
def get_sync_url(url: str) -> str:
    """Convert async database URL to sync."""
    return url.replace("+aiosqlite", "").replace("sqlite:///", "sqlite:///")


# Create engine
_sync_url = get_sync_url(settings.database_url)

# For SQLite, use check_same_thread=False for multi-threaded access
if "sqlite" in _sync_url:
    engine = create_engine(
        _sync_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=settings.debug and settings.app_env == "development"
    )
    
    # Enable foreign keys for SQLite
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
else:
    engine = create_engine(
        _sync_url,
        pool_size=5,
        max_overflow=10,
        echo=settings.debug and settings.app_env == "development"
    )


# Session factory
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False
)


def init_db() -> None:
    """Initialize database - create all tables."""
    # Ensure data directory exists for SQLite
    if "sqlite" in settings.database_url:
        db_path = settings.database_url.split("///")[-1]
        if db_path.startswith("./"):
            db_path = db_path[2:]
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    logger.info("database_initialized", tables=list(Base.metadata.tables.keys()))


def drop_db() -> None:
    """Drop all tables - use with caution!"""
    Base.metadata.drop_all(bind=engine)
    logger.warning("database_dropped")


@contextmanager
def get_db() -> Generator[Session, None, None]:
    """Get database session context manager."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error("database_error", error=str(e))
        raise
    finally:
        session.close()


def get_db_session() -> Session:
    """Get a new database session (caller must manage lifecycle)."""
    return SessionLocal()


# Dependency for FastAPI
def get_db_dependency() -> Generator[Session, None, None]:
    """FastAPI dependency for database session."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


class DatabaseService:
    """
    High-level database service for common operations.
    """
    
    def __init__(self):
        self.logger = structlog.get_logger().bind(service="database")
    
    def health_check(self) -> bool:
        """Check database connectivity."""
        try:
            with get_db() as db:
                db.execute(text("SELECT 1"))
            return True
        except Exception as e:
            self.logger.error("health_check_failed", error=str(e))
            return False
    
    def get_stats(self) -> dict:
        """Get database statistics."""
        from app.models.database import (
            EntityModel, PeriodModel, BalanceModel, 
            DecisionModel, FeedbackModel, AuditLogModel
        )
        
        with get_db() as db:
            return {
                "entities": db.query(EntityModel).count(),
                "periods": db.query(PeriodModel).count(),
                "balances": db.query(BalanceModel).count(),
                "decisions": db.query(DecisionModel).count(),
                "feedback": db.query(FeedbackModel).count(),
                "audit_logs": db.query(AuditLogModel).count()
            }


# Global service instance
_db_service: DatabaseService | None = None


def get_database_service() -> DatabaseService:
    """Get global database service instance."""
    global _db_service
    if _db_service is None:
        _db_service = DatabaseService()
    return _db_service
