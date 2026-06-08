import os
from contextlib import asynccontextmanager
from urllib.parse import urlparse

import anyio
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

load_dotenv()
DATABASE_URL = os.getenv('FILAMENT_DB_URI', 'sqlite://filament.db')

_AIO_SCHEMES = {
    'postgresql': 'postgresql+asyncpg',
}


def convert_to_async_url(url):
    parts = urlparse(url)
    scheme = parts.scheme
    if scheme not in _AIO_SCHEMES:
        raise ValueError(f'Unsupported async scheme: {scheme}')
    scheme = _AIO_SCHEMES[scheme]
    parts = parts._replace(scheme=scheme)
    return parts.geturl()


engine = create_async_engine(convert_to_async_url(DATABASE_URL), pool_size=10, max_overflow=100)
AsyncSession = async_sessionmaker(bind=engine)


@asynccontextmanager
async def async_session_scope(commit=True, autoflush=True):
    with anyio.CancelScope(shield=True):
        async with AsyncSession(autoflush=autoflush) as session:
            yield session
            if commit:
                await session.commit()
