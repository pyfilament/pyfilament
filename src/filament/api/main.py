from filament.api.setup_logging import setup_logging

setup_logging()

import filament.api.routes  # noqa: F401
from filament.api.app import app
from filament.api.graphql import graphql_app
from filament.api.middleware import SessionMiddleware

app.add_middleware(SessionMiddleware)
app.include_router(graphql_app, prefix='/graphql')
