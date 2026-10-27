from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


def make_engine(database_url: str, pool_size: int = 10) -> AsyncEngine:
    # Supabase hands out plain postgresql:// URLs; SQLAlchemy needs the async driver named.
    url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1).replace(
        "postgres://", "postgresql+asyncpg://", 1
    )
    return create_async_engine(url, pool_size=pool_size, pool_pre_ping=True)
