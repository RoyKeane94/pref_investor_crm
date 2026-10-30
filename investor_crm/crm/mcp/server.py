"""MCP Streamable HTTP server mounted at /mcp/."""

from __future__ import annotations

from asgiref.sync import sync_to_async
from django.conf import settings

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from crm.mcp.auth import AgentBearerAuthMiddleware, get_current_agent_user_id
from crm.mcp import tools as tool_impl

mcp = MCPServer(
    name='PrefEquity Investor CRM',
    instructions=(
        'Read-only CRM access for agent accounts, plus create/update/delete '
        'findings the agent authored. Authenticate with '
        'Authorization: Bearer <agent API token> (no OAuth).'
    ),
)


def _current_user_id() -> int | None:
    return get_current_agent_user_id()


def _transport_security() -> TransportSecuritySettings:
    # Hosted behind Railway TLS with bearer API keys. DNS-rebinding checks
    # reject Anthropic/Claude Origin headers and misconfigured ALLOWED_HOSTS,
    # which shows up as a vague "connection" failure in Claude.
    if getattr(settings, 'MCP_DISABLE_DNS_REBINDING_PROTECTION', True):
        return TransportSecuritySettings(enable_dns_rebinding_protection=False)

    hosts = list(getattr(settings, 'MCP_ALLOWED_HOSTS', None) or [])
    origins = list(getattr(settings, 'MCP_ALLOWED_ORIGINS', None) or [])
    if not hosts:
        hosts = ['127.0.0.1', 'localhost', '127.0.0.1:*', 'localhost:*']
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=hosts,
        allowed_origins=origins,
    )


def build_mcp_http_app():
    """ASGI app for Streamable HTTP. Mount at /mcp with path=/."""
    app = mcp.streamable_http_app(
        streamable_http_path='/',
        json_response=True,
        stateless_http=True,
        transport_security=_transport_security(),
    )
    # Bearer API keys only — avoid MCP OAuth AuthSettings, which makes Claude
    # probe /.well-known/oauth-* (those routes are not on the Django root).
    return AgentBearerAuthMiddleware(app)


@mcp.tool(
    name='search_investors',
    description=(
        'Search investors by name or principal-contact text, with optional '
        'status and type filters. Returns a paged list (page_size up to 500). '
        'investor_type must be one of: asset_manager, bank, endowment_charity, '
        'fund_manager, fund_of_funds, gatekeeper_consultant, hnw_uhnw, '
        'insurance_company, investment_company_trust, pension_fund_company, '
        'lgps, lgps_pool, single_family_office, swf_government, '
        'wealth_manager_pb_mfo. '
        'status must be one of: target_sma, target_feeder_fund, target_fund_iii, '
        'confirmed_sma, confirmed_feeder_fund, confirmed_fund_iii, other, '
        'confirmed, dead. '
        'Note: "other" is a status, not an investor_type. Invalid filters return '
        'an error object listing valid_investor_types and valid_statuses.'
    ),
)
async def search_investors(
    query: str = '',
    status: str = '',
    investor_type: str = '',
    page: int = 1,
    page_size: int = 25,
) -> dict:
    return await sync_to_async(tool_impl.search_investors, thread_sensitive=True)(
        _current_user_id(),
        query=query,
        status=status,
        investor_type=investor_type,
        page=page,
        page_size=page_size,
    )


@mcp.tool(
    name='get_investor',
    description=(
        'Get one investor by ID, including contacts (id, role/title), '
        'recent activity, commitments, co-investments, and findings.'
    ),
)
async def get_investor(investor_id: int) -> dict:
    return await sync_to_async(tool_impl.get_investor, thread_sensitive=True)(
        _current_user_id(),
        investor_id,
    )


@mcp.tool(
    name='list_findings',
    description=(
        'List agent findings (AgentNotes). Filters: investor_id, source_url '
        'substring, type (news|person_change|investment|flag|fit_flag|checked|'
        'note), date_from/date_to = source event_date, logged_from/logged_to = '
        'when the entry was logged (created_at, YYYY-MM-DD). '
        'Paged; page_size up to 500.'
    ),
)
async def list_findings(
    investor_id: int | None = None,
    source_url: str = '',
    type: str = '',
    date_from: str = '',
    date_to: str = '',
    logged_from: str = '',
    logged_to: str = '',
    page: int = 1,
    page_size: int = 25,
) -> dict:
    return await sync_to_async(tool_impl.list_findings, thread_sensitive=True)(
        _current_user_id(),
        investor_id=investor_id,
        source_url=source_url,
        type=type,
        date_from=date_from,
        date_to=date_to,
        logged_from=logged_from,
        logged_to=logged_to,
        page=page,
        page_size=page_size,
    )


@mcp.tool(
    name='add_finding',
    description=(
        'Create a finding for an investor. Types: news, person_change, '
        'investment, flag, fit_flag, checked, note. '
        'flag = team should look into this investor (headline/detail = why). '
        'fit_flag = looks like a fund fit (headline/detail = why). '
        'checked = agent reviewed this investor (headline/detail optional). '
        'note = general comment. News requires source_url. Personnel changes '
        'require person; optional from/to. Always pass event_date (YYYY-MM-DD) '
        'when the source/event date is known. Optional confidence '
        '(low|medium|high). Do not use news for fit flags or checked marks.'
    ),
)
async def add_finding(
    investor_id: int,
    type: str,
    headline: str = '',
    source_url: str = '',
    detail: str = '',
    event_date: str = '',
    confidence: str = '',
    person: str = '',
    moved_from: str = '',
    moved_to: str = '',
) -> dict:
    return await sync_to_async(tool_impl.add_finding, thread_sensitive=True)(
        _current_user_id(),
        investor_id=investor_id,
        type=type,
        headline=headline,
        source_url=source_url,
        detail=detail,
        event_date=event_date,
        confidence=confidence,
        person=person,
        moved_from=moved_from,
        moved_to=moved_to,
    )


@mcp.tool(
    name='update_finding',
    description=(
        'Update a finding the authenticated agent created. Omit fields you '
        'do not want to change. Pass empty strings to clear optional text fields. '
        'To clear event_date: pass "", null, "null", "clear", or clear_event_date=true.'
    ),
)
async def update_finding(
    finding_id: int,
    type: str | None = None,
    headline: str | None = None,
    source_url: str | None = None,
    detail: str | None = None,
    event_date: str | None = tool_impl.EVENT_DATE_OMIT,
    clear_event_date: bool = False,
    confidence: str | None = None,
    person: str | None = None,
    moved_from: str | None = None,
    moved_to: str | None = None,
) -> dict:
    return await sync_to_async(tool_impl.update_finding, thread_sensitive=True)(
        _current_user_id(),
        finding_id,
        type=type,
        headline=headline,
        source_url=source_url,
        detail=detail,
        event_date=event_date,
        clear_event_date=clear_event_date,
        confidence=confidence,
        person=person,
        moved_from=moved_from,
        moved_to=moved_to,
    )


@mcp.tool(
    name='bulk_add_findings',
    description=(
        'Create up to 100 findings in one call. Pass findings as a list of objects, '
        'each with the same fields as add_finding (investor_id, type, and optional '
        'headline, detail, source_url, event_date, confidence, person, moved_from, '
        'moved_to). Returns created[] and errors[] (per-index). Prefer this over '
        'many add_finding calls.'
    ),
)
async def bulk_add_findings(findings: list[dict]) -> dict:
    return await sync_to_async(tool_impl.bulk_add_findings, thread_sensitive=True)(
        _current_user_id(),
        findings,
    )


@mcp.tool(
    name='bulk_update_findings',
    description=(
        'Update up to 100 findings in one call. Pass updates as a list of objects, '
        'each with finding_id (or id) plus fields to change (same as update_finding). '
        'To clear event_date on an item: set event_date to "", null, "null", or '
        'clear_event_date=true. Returns updated[] and errors[]. Prefer this over '
        'many update_finding calls.'
    ),
)
async def bulk_update_findings(updates: list[dict]) -> dict:
    return await sync_to_async(tool_impl.bulk_update_findings, thread_sensitive=True)(
        _current_user_id(),
        updates,
    )


@mcp.tool(
    name='delete_finding',
    description='Delete a finding the authenticated agent created.',
)
async def delete_finding(finding_id: int) -> dict:
    return await sync_to_async(tool_impl.delete_finding, thread_sensitive=True)(
        _current_user_id(),
        finding_id,
    )
