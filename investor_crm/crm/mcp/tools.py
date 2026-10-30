"""Business logic for MCP tools (runs in sync Django ORM context)."""

from __future__ import annotations

from datetime import date
from typing import Any

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import close_old_connections
from django.db.models import Prefetch, Q
from django.utils.dateparse import parse_date, parse_datetime

from crm.models import AgentNote, Investor
from crm.mcp.serializers import (
    serialize_finding,
    serialize_investor_detail,
    serialize_investor_summary,
)
from crm.permissions import can_edit_agent_note, is_agent_user

VALID_NOTE_TYPES = {c[0] for c in AgentNote.NOTE_TYPE_CHOICES}
VALID_CONFIDENCE = {c[0] for c in AgentNote.CONFIDENCE_CHOICES}
VALID_INVESTOR_TYPES = {c[0] for c in Investor.TYPE_CHOICES}
VALID_STATUSES = {c[0] for c in Investor.STATUS_CHOICES}


def _close() -> None:
    close_old_connections()


def _require_agent(user_id: int | None) -> User:
    if user_id is None:
        raise PermissionError('Authentication required.')
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist as exc:
        raise PermissionError('Authentication required.') from exc
    if not user.is_active or not is_agent_user(user):
        raise PermissionError('Agent account required.')
    return user


def _parse_optional_date(value: str | None, field_name: str) -> date | None:
    if value is None or str(value).strip() == '':
        return None
    text = str(value).strip()
    parsed = parse_date(text)
    if parsed is None:
        dt = parse_datetime(text)
        if dt is not None:
            parsed = dt.date()
    if parsed is None:
        raise ValueError(f'Invalid {field_name}: use YYYY-MM-DD.')
    return parsed


def _validate_finding_fields(
    *,
    note_type: str,
    headline: str,
    detail: str,
    source_url: str,
    person: str,
    confidence: str,
) -> None:
    if note_type not in VALID_NOTE_TYPES:
        raise ValueError(
            f'Invalid type. Choose one of: {", ".join(sorted(VALID_NOTE_TYPES))}.'
        )
    if confidence and confidence not in VALID_CONFIDENCE:
        raise ValueError(
            f'Invalid confidence. Choose one of: {", ".join(sorted(VALID_CONFIDENCE))}.'
        )
    if note_type == 'person_change' and not person.strip():
        raise ValueError('person is required for personnel-change findings.')
    if note_type == 'news':
        if not headline.strip() and not detail.strip():
            raise ValueError('headline or detail is required for news findings.')
        if not source_url.strip():
            raise ValueError('source_url is required for news findings.')
    if note_type == 'investment' and not headline.strip() and not detail.strip():
        raise ValueError('headline or detail is required for investment findings.')
    if note_type == 'flag' and not headline.strip() and not detail.strip():
        raise ValueError(
            'headline or detail is required for flag findings '
            '(why the team should look into this investor).'
        )


def search_investors(
    user_id: int | None,
    *,
    query: str = '',
    status: str = '',
    investor_type: str = '',
    page: int = 1,
    page_size: int = 25,
) -> dict[str, Any]:
    _close()
    try:
        _require_agent(user_id)
        qs = Investor.objects.select_related('office').all()
        q = (query or '').strip()
        if q:
            # "alias" soft-match: name or principal contact (no dedicated aliases field)
            qs = qs.filter(
                Q(name__icontains=q) | Q(principal_contact__icontains=q)
            )
        status = (status or '').strip()
        if status:
            if status not in VALID_STATUSES:
                raise ValueError(
                    f'Invalid status. Choose one of: {", ".join(sorted(VALID_STATUSES))}.'
                )
            qs = qs.filter(statuses__contains=[status])
        investor_type = (investor_type or '').strip()
        if investor_type:
            if investor_type not in VALID_INVESTOR_TYPES:
                raise ValueError(
                    'Invalid type. Choose one of: '
                    + ', '.join(sorted(VALID_INVESTOR_TYPES))
                    + '.'
                )
            qs = qs.filter(type=investor_type)

        page = max(1, int(page or 1))
        page_size = min(100, max(1, int(page_size or 25)))
        paginator = Paginator(qs.order_by('name'), page_size)
        page_obj = paginator.get_page(page)
        return {
            'page': page_obj.number,
            'page_size': page_size,
            'total': paginator.count,
            'total_pages': paginator.num_pages,
            'results': [serialize_investor_summary(inv) for inv in page_obj.object_list],
        }
    finally:
        _close()


def get_investor(user_id: int | None, investor_id: int) -> dict[str, Any]:
    _close()
    try:
        _require_agent(user_id)
        investor = (
            Investor.objects.select_related(
                'office', 'responsibility', 'intermediary'
            )
            .prefetch_related(
                'contacts',
                'meeting_logs',
                'call_logs',
                'email_logs',
                'commitments',
                'co_investments',
                Prefetch(
                    'agent_notes',
                    queryset=AgentNote.objects.select_related('author', 'investor'),
                ),
            )
            .filter(pk=investor_id)
            .first()
        )
        if investor is None:
            raise ValueError(f'Investor {investor_id} not found.')
        return serialize_investor_detail(investor)
    finally:
        _close()


def list_findings(
    user_id: int | None,
    *,
    investor_id: int | None = None,
    source_url: str = '',
    date_from: str = '',
    date_to: str = '',
    page: int = 1,
    page_size: int = 25,
) -> dict[str, Any]:
    _close()
    try:
        _require_agent(user_id)
        qs = AgentNote.objects.select_related('investor', 'author').all()
        if investor_id is not None:
            qs = qs.filter(investor_id=investor_id)
        source_url = (source_url or '').strip()
        if source_url:
            qs = qs.filter(link__icontains=source_url)
        d_from = _parse_optional_date(date_from or None, 'date_from')
        d_to = _parse_optional_date(date_to or None, 'date_to')
        if d_from:
            qs = qs.filter(
                Q(event_date__gte=d_from)
                | Q(event_date__isnull=True, created_at__date__gte=d_from)
            )
        if d_to:
            qs = qs.filter(
                Q(event_date__lte=d_to)
                | Q(event_date__isnull=True, created_at__date__lte=d_to)
            )

        page = max(1, int(page or 1))
        page_size = min(100, max(1, int(page_size or 25)))
        paginator = Paginator(qs.order_by('-created_at'), page_size)
        page_obj = paginator.get_page(page)
        return {
            'page': page_obj.number,
            'page_size': page_size,
            'total': paginator.count,
            'total_pages': paginator.num_pages,
            'results': [serialize_finding(n) for n in page_obj.object_list],
        }
    finally:
        _close()


def add_finding(
    user_id: int | None,
    *,
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
) -> dict[str, Any]:
    _close()
    try:
        user = _require_agent(user_id)
        note_type = (type or '').strip()
        headline = (headline or '').strip()
        detail = (detail or '').strip()
        source_url = (source_url or '').strip()
        person = (person or '').strip()
        confidence = (confidence or '').strip()
        moved_from = (moved_from or '').strip()
        moved_to = (moved_to or '').strip()
        _validate_finding_fields(
            note_type=note_type,
            headline=headline,
            detail=detail,
            source_url=source_url,
            person=person,
            confidence=confidence,
        )
        if not Investor.objects.filter(pk=investor_id).exists():
            raise ValueError(f'Investor {investor_id} not found.')
        parsed_event = _parse_optional_date(event_date or None, 'event_date')
        note = AgentNote(
            investor_id=investor_id,
            author=user,
            note_type=note_type,
            title=headline,
            body=detail,
            link=source_url,
            person_name=person,
            moved_from=moved_from,
            moved_to=moved_to,
            event_date=parsed_event,
            confidence=confidence,
        )
        try:
            note.full_clean()
        except ValidationError as exc:
            raise ValueError('; '.join(
                f'{k}: {", ".join(v)}' for k, v in exc.message_dict.items()
            )) from exc
        note.save()
        note = AgentNote.objects.select_related('investor', 'author').get(pk=note.pk)
        return serialize_finding(note)
    finally:
        _close()


def update_finding(
    user_id: int | None,
    finding_id: int,
    *,
    type: str | None = None,
    headline: str | None = None,
    source_url: str | None = None,
    detail: str | None = None,
    event_date: str | None = None,
    confidence: str | None = None,
    person: str | None = None,
    moved_from: str | None = None,
    moved_to: str | None = None,
) -> dict[str, Any]:
    _close()
    try:
        user = _require_agent(user_id)
        note = (
            AgentNote.objects.select_related('investor', 'author')
            .filter(pk=finding_id)
            .first()
        )
        if note is None:
            raise ValueError(f'Finding {finding_id} not found.')
        if not can_edit_agent_note(user, note):
            raise PermissionError(
                'You can only update findings you created.'
            )

        if type is not None:
            note.note_type = type.strip()
        if headline is not None:
            note.title = headline.strip()
        if detail is not None:
            note.body = detail.strip()
        if source_url is not None:
            note.link = source_url.strip()
        if person is not None:
            note.person_name = person.strip()
        if moved_from is not None:
            note.moved_from = moved_from.strip()
        if moved_to is not None:
            note.moved_to = moved_to.strip()
        if confidence is not None:
            note.confidence = confidence.strip()
        if event_date is not None:
            note.event_date = _parse_optional_date(event_date or None, 'event_date')

        _validate_finding_fields(
            note_type=note.note_type,
            headline=note.title or '',
            detail=note.body or '',
            source_url=note.link or '',
            person=note.person_name or '',
            confidence=note.confidence or '',
        )
        try:
            note.full_clean()
        except ValidationError as exc:
            raise ValueError('; '.join(
                f'{k}: {", ".join(v)}' for k, v in exc.message_dict.items()
            )) from exc
        note.save()
        note = AgentNote.objects.select_related('investor', 'author').get(pk=note.pk)
        return serialize_finding(note)
    finally:
        _close()


def delete_finding(user_id: int | None, finding_id: int) -> dict[str, Any]:
    _close()
    try:
        user = _require_agent(user_id)
        note = AgentNote.objects.filter(pk=finding_id).first()
        if note is None:
            raise ValueError(f'Finding {finding_id} not found.')
        if not can_edit_agent_note(user, note):
            raise PermissionError(
                'You can only delete findings you created.'
            )
        note.delete()
        return {'deleted': True, 'id': finding_id}
    finally:
        _close()
