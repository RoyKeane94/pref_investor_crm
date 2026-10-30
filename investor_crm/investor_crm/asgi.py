"""
ASGI config for investor_crm project.

Mounts the MCP Streamable HTTP app at /mcp/ alongside Django.
"""

import os
from contextlib import asynccontextmanager

from django.core.asgi import get_asgi_application
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import RedirectResponse
from starlette.routing import Mount, Route

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'investor_crm.settings')

django_application = get_asgi_application()

from crm.mcp.server import build_mcp_http_app, mcp  # noqa: E402

mcp_http_app = build_mcp_http_app()


async def redirect_mcp(request: Request) -> RedirectResponse:
    return RedirectResponse(str(request.url.replace(path='/mcp/')), status_code=307)


@asynccontextmanager
async def lifespan(app: Starlette):
    async with mcp.session_manager.run():
        yield


application = Starlette(
    routes=[
        Route('/mcp', endpoint=redirect_mcp, methods=['GET', 'POST', 'DELETE']),
        Mount('/mcp', app=mcp_http_app),
        Mount('/', app=django_application),
    ],
    lifespan=lifespan,
)
