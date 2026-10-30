"""Bearer-token verification for the MCP endpoint."""

from __future__ import annotations

from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import close_old_connections

from mcp.server.auth.provider import AccessToken, TokenVerifier

from crm.models import AgentApiToken
from crm.permissions import is_agent_user

AGENT_SCOPE = 'agent'


def _lookup_access_token(raw_token: str) -> AccessToken | None:
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
        resource = getattr(settings, 'MCP_PUBLIC_URL', None) or None
        return AccessToken(
            token=raw_token,
            client_id=str(user.pk),
            scopes=[AGENT_SCOPE],
            subject=str(user.pk),
            claims={
                'user_id': user.pk,
                'email': user.email or user.username,
            },
            resource=resource,
        )
    finally:
        close_old_connections()


class AgentTokenVerifier(TokenVerifier):
    """Validate Authorization: Bearer tokens issued to agent accounts."""

    async def verify_token(self, token: str) -> AccessToken | None:
        return await sync_to_async(_lookup_access_token, thread_sensitive=True)(token)


def user_id_from_access_token(access: AccessToken | None) -> int | None:
    if access is None:
        return None
    if access.claims and access.claims.get('user_id') is not None:
        try:
            return int(access.claims['user_id'])
        except (TypeError, ValueError):
            pass
    if access.subject:
        try:
            return int(access.subject)
        except (TypeError, ValueError):
            pass
    try:
        return int(access.client_id)
    except (TypeError, ValueError):
        return None
