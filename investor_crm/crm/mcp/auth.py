"""Bearer-token verification for the MCP endpoint (no OAuth)."""

from __future__ import annotations

import logging
from contextvars import ContextVar

from asgiref.sync import sync_to_async
from django.db import close_old_connections
from starlette.types import ASGIApp, Receive, Scope, Send

from crm.models import AgentApiToken
from crm.permissions import is_agent_user

logger = logging.getLogger('crm.mcp.auth')

_current_agent_user_id: ContextVar[int | None] = ContextVar(
    'mcp_agent_user_id', default=None
)


def get_current_agent_user_id() -> int | None:
    return _current_agent_user_id.get()


def lookup_agent_user_id(raw_token: str) -> tuple[int | None, str]:
    """Return (user_id, reason). reason is empty on success."""
    close_old_connections()
    try:
        if not raw_token:
            return None, 'missing_bearer_token'
        key_hash = AgentApiToken.hash_key(raw_token)
        api_token = (
            AgentApiToken.objects.select_related('user')
            .filter(key_hash=key_hash)
            .first()
        )
        if api_token is None:
            return None, 'unknown_token'
        if api_token.revoked_at is not None:
            return None, f'revoked_token prefix={api_token.prefix}'
        user = api_token.user
        if not user.is_active:
            return None, f'inactive_user id={user.pk}'
        if not is_agent_user(user):
            return None, f'not_agent_user id={user.pk} email={user.email or user.username}'
        api_token.mark_used()
        return user.pk, ''
    finally:
        close_old_connections()


def _bearer_from_scope(scope: Scope) -> tuple[str, str]:
    """Return (raw_token, parse_note)."""
    for key, value in scope.get('headers') or []:
        if key.decode('latin-1').lower() == 'authorization':
            auth = value.decode('latin-1')
            scheme, _, token = auth.partition(' ')
            if scheme.lower() == 'bearer' and token.strip():
                return token.strip(), ''
            if not scheme:
                return '', 'empty_authorization_header'
            return '', f'non_bearer_scheme scheme={scheme!r}'
    return '', 'no_authorization_header'


def _request_path(scope: Scope) -> str:
    path = scope.get('path') or '/'
    qs = scope.get('query_string') or b''
    if qs:
        return f'{path}?{qs.decode("latin-1", errors="replace")}'
    return path


class AgentBearerAuthMiddleware:
    """Require Authorization: Bearer <agent token>; do not advertise OAuth."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return

        method = scope.get('method', '?')
        path = _request_path(scope)
        raw, parse_note = _bearer_from_scope(scope)
        user_id = None
        reason = parse_note or 'missing_bearer_token'
        if raw:
            user_id, reason = await sync_to_async(
                lookup_agent_user_id, thread_sensitive=True
            )(raw)

        if user_id is None:
            logger.warning(
                'MCP auth rejected method=%s path=%s reason=%s',
                method,
                path,
                reason,
            )
            body = (
                b'{"error":"invalid_token",'
                b'"error_description":"Authentication required. '
                b'Use Authorization: Bearer <agent API token>."}'
            )
            # Do not send WWW-Authenticate — Claude treats that as an OAuth
            # challenge and then fails on missing /.well-known/oauth-* routes.
            await send(
                {
                    'type': 'http.response.start',
                    'status': 401,
                    'headers': [
                        (b'content-type', b'application/json'),
                        (b'content-length', str(len(body)).encode('ascii')),
                    ],
                }
            )
            await send({'type': 'http.response.body', 'body': body})
            return

        logger.info(
            'MCP auth ok method=%s path=%s user_id=%s',
            method,
            path,
            user_id,
        )
        token = _current_agent_user_id.set(user_id)
        try:
            await self.app(scope, receive, send)
        finally:
            _current_agent_user_id.reset(token)
