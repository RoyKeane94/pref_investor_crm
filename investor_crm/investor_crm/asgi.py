"""
ASGI config for investor_crm project.

Mounts the MCP Streamable HTTP app at /mcp/ alongside Django.
"""

import os
from contextlib import asynccontextmanager

from django.core.asgi import get_asgi_application
from starlette.applications import Starlette
from starlette.routing import Mount, Route
from starlette.types import ASGIApp, Receive, Scope, Send

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'investor_crm.settings')

django_application = get_asgi_application()

from crm.mcp.server import build_mcp_http_app, mcp  # noqa: E402

mcp_http_app = build_mcp_http_app()


class McpNoSlashForward:
    """Serve /mcp without an HTTP redirect.

    A 307 /mcp → /mcp/ drops Authorization on Claude (and many other clients),
    which then shows up as MCP auth reason=no_authorization_header.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] == 'http':
            scope = dict(scope)
            # Same scope Mount('/mcp', ...) would pass for /mcp/.
            scope['path'] = '/'
            root = scope.get('root_path') or ''
            scope['root_path'] = root.rstrip('/') + '/mcp'
        await self.app(scope, receive, send)


@asynccontextmanager
async def lifespan(app: Starlette):
    async with mcp.session_manager.run():
        yield


application = Starlette(
    routes=[
        Route(
            '/mcp',
            endpoint=McpNoSlashForward(mcp_http_app),
            methods=['GET', 'POST', 'DELETE'],
        ),
        Mount('/mcp', app=mcp_http_app),
        Mount('/', app=django_application),
    ],
    lifespan=lifespan,
)
