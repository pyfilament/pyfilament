from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from filament.db_session import async_session_scope


class SessionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        async with async_session_scope() as session:
            request.state.session = session
            return await call_next(request)
