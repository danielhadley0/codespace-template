"""
Database connection management.
"""
import asyncio
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker
)
from sqlalchemy.pool import NullPool
from contextlib import asynccontextmanager
import structlog

from config.settings import settings
from src.database.models import Base

logger = structlog.get_logger()


class DatabaseManager:
    """Manages database connections and sessions."""

    def __init__(self):
        self.engine = None
        self.async_session_maker = None

    async def initialize(self):
        """Initialize database engine and create tables."""
        try:
            # Convert postgresql:// to postgresql+asyncpg://
            db_url = settings.database_url
            if db_url.startswith('postgresql://'):
                db_url = db_url.replace('postgresql://', 'postgresql+asyncpg://', 1)
            elif not db_url.startswith('postgresql+asyncpg://'):
                db_url = f'postgresql+asyncpg://{db_url}'

            self.engine = create_async_engine(
                db_url,
                echo=settings.log_level == 'DEBUG',
                poolclass=NullPool,
                pool_pre_ping=True,
            )

            self.async_session_maker = async_sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )

            # Create all tables
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            logger.info("Database initialized successfully")

        except Exception as e:
            logger.error("Failed to initialize database", error=str(e))
            raise

    async def close(self):
        """Close database connections."""
        if self.engine:
            await self.engine.dispose()
            logger.info("Database connections closed")

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Provide a transactional scope for database operations.

        Usage:
            async with db_manager.session() as session:
                # Do database operations
                result = await session.execute(query)
        """
        if not self.async_session_maker:
            raise RuntimeError("Database not initialized. Call initialize() first.")

        async with self.async_session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.error("Database transaction failed", error=str(e))
                raise
            finally:
                await session.close()


# Global database manager instance
db_manager = DatabaseManager()
