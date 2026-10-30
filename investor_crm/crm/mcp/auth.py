"""Bearer-token verification for the MCP endpoint (no OAuth)."""

from __future__ import annotations

from contextvars import ContextVar

from asgiref.sync import sync_to_async
from django.db import close_old_connections
from starlette.types import ASGIApp, Receive, Scope, Send

from crm.models import AgentApiToken
from crm.permissions import is_agent_user

_current_agent_user_id: ContextVar[int | None] = ContextVar(
    'mcp_agent_user_id', default=None
)


def get_current_agent_user_id() -> int | None:
    return _current_agent_user_id.get()


def lookup_agent_user_id(raw_token: str) -> int | None:
    """Return the agent user id for a raw bearer token, or None."""
    close_old_connections()
    try:
        if not raw_token:
            return None
        key_hash = AgentApiToken.hash_key(raw_token)
        api_token = (
            AgentApiToken.objects.select_related('user')
            .filter(key_hash=key_hash, revoked_at__isnull=True)
            .first()
        )
        if api_token is None:
            return None
        user = api_token.user
        if not user.is_active or not is_agent_user(user):
            return None
        api_token.mark_used()
        return user.pk
    finally:
        close_old_connections()


def _bearer_from_scope(scope: Scope) -> str:
    for key, value in scope.get('headers') or []:
        if key.decode('latin-1').lower() == 'authorization':
            auth = value.decode('latin-1')
            scheme, _, token = auth.partition(' ')
            if scheme.lower() == 'bearer' and token.strip():
                return token.strip()
            return ''
    return ''


class AgentBearerAuthMiddleware:
    """Require Authorization: Bearer <agent token>; do not advertise OAuth."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return

        # CORS / probes without credentials: still require bearer for MCP.
        raw = _bearer_from_scope(scope)
        user_id = None
        if raw:
            user_id = await sync_to_async(
                lookup_agent_user_id, thread_sensitive=True
            )(raw)

        if user_id is None:
            body = (
                b'{"error":"invalid_token",'
                b'"error_description":"Authentication required. '
                b'Use Authorization: Bearer <agent API token>."}'
            )
            await send(
                {
                    'type': 'http.response.start',
                    'status': 401,
                    'headers': [
                        (b'content-type', b'application/json'),
                        (b'www-authenticate', b'Bearer'),
                        (b'content-length', str(len(body)).encode('ascii')),
                    ],
                }
            )
            await send({'type': 'http.response.body', 'body': body})
            return

        token = _current_agent_user_id.set(user_id)
        try:
            await self.app(scope, receive, send)
        finally:
            _current_agent_user_id.reset(token)
