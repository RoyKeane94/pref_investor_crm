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
INVESTOR_TYPE_VALUES = [c[0] for c in Investor.TYPE_CHOICES]
STATUS_VALUES = [c[0] for c in Investor.STATUS_CHOICES]
MAX_PAGE_SIZE = 500
MAX_BULK_FINDINGS = 100
# Agents often send null/blank/"null" when clearing optional dates.
_CLEAR_DATE_TOKENS = frozenset({
    '',
    'null',
    'none',
    'nil',
    'clear',
    '-',
    'n/a',
    'na',
})


def _filter_error(field: str, value: str) -> dict[str, Any]:
    """Structured error so agents see valid enums instead of a bare tool failure."""
    tip = ''
    if field == 'investor_type' and value in VALID_STATUSES:
        tip = (
            f' "{value}" is a status value, not an investor type — '
            f'pass it as status="{value}" instead.'
        )
    elif field == 'status' and value in VALID_INVESTOR_TYPES:
        tip = (
            f' "{value}" is an investor type, not a status — '
            f'pass it as investor_type="{value}" instead.'
        )
    return {
        'error': f'Invalid {field}={value!r}.{tip}',
        'valid_investor_types': INVESTOR_TYPE_VALUES,
        'valid_statuses': STATUS_VALUES,
    }


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


def _is_clear_date_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip().lower() in _CLEAR_DATE_TOKENS:
        return True
    return False


def _parse_optional_date(value: Any, field_name: str) -> date | None:
    """Parse YYYY-MM-DD, or return None to clear. Accepts '', null, 'null', 'clear', etc."""
    if _is_clear_date_value(value):
        return None
    text = str(value).strip()
    parsed = parse_date(text)
    if parsed is None:
        dt = parse_datetime(text)
        if dt is not None:
            parsed = dt.date()
    if parsed is None:
        raise ValueError(
            f'Invalid {field_name}: use YYYY-MM-DD, or empty/null/clear to clear.'
        )
    return parsed


def _clamp_page_size(page_size: int | None, default: int = 25) -> int:
    return min(MAX_PAGE_SIZE, max(1, int(page_size or default)))


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
    if note_type == 'fit_flag' and not headline.strip() and not detail.strip():
        raise ValueError(
            'headline or detail is required for fit_flag '
            '(why this investor looks like a fit).'
        )
    if note_type == 'note' and not headline.strip() and not detail.strip():
        raise ValueError('headline or detail is required for notes.')
    # checked: optional headline/detail


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
                return _filter_error('status', status)
            qs = qs.filter(statuses__contains=[status])
        investor_type = (investor_type or '').strip()
        if investor_type:
            if investor_type not in VALID_INVESTOR_TYPES:
                return _filter_error('investor_type', investor_type)
            qs = qs.filter(type=investor_type)

        page = max(1, int(page or 1))
        page_size = _clamp_page_size(page_size)
        paginator = Paginator(qs.order_by('name'), page_size)
        page_obj = paginator.get_page(page)
        return {
            'page': page_obj.number,
            'page_size': page_size,
            'total': paginator.count,
            'total_pages': paginator.num_pages,
            'max_page_size': MAX_PAGE_SIZE,
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
    type: str = '',
    date_from: str = '',
    date_to: str = '',
    logged_from: str = '',
    logged_to: str = '',
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
        note_type = (type or '').strip()
        if note_type:
            if note_type not in VALID_NOTE_TYPES:
                return {
                    'error': f'Invalid type={note_type!r}.',
                    'valid_types': sorted(VALID_NOTE_TYPES),
                }
            qs = qs.filter(note_type=note_type)
        # Source / event date on the finding
        d_from = _parse_optional_date(date_from or None, 'date_from')
        d_to = _parse_optional_date(date_to or None, 'date_to')
        if d_from:
            qs = qs.filter(event_date__gte=d_from)
        if d_to:
            qs = qs.filter(event_date__lte=d_to)
        # When the agent logged the entry (created_at)
        log_from = _parse_optional_date(logged_from or None, 'logged_from')
        log_to = _parse_optional_date(logged_to or None, 'logged_to')
        if log_from:
            qs = qs.filter(created_at__date__gte=log_from)
        if log_to:
            qs = qs.filter(created_at__date__lte=log_to)

        page = max(1, int(page or 1))
        page_size = _clamp_page_size(page_size)
        paginator = Paginator(qs.order_by('-created_at'), page_size)
        page_obj = paginator.get_page(page)
        return {
            'page': page_obj.number,
            'page_size': page_size,
            'total': paginator.count,
            'total_pages': paginator.num_pages,
            'max_page_size': MAX_PAGE_SIZE,
            'results': [serialize_finding(n) for n in page_obj.object_list],
        }
    finally:
        _close()


def _validation_error_message(exc: ValidationError) -> str:
    return '; '.join(
        f'{k}: {", ".join(v)}' for k, v in exc.message_dict.items()
    )


def _create_finding_for_user(user: User, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        investor_id = int(payload['investor_id'])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError('investor_id is required and must be an integer.') from exc
    note_type = str(payload.get('type') or '').strip()
    headline = str(payload.get('headline') or '').strip()
    detail = str(payload.get('detail') or '').strip()
    source_url = str(payload.get('source_url') or '').strip()
    person = str(payload.get('person') or '').strip()
    confidence = str(payload.get('confidence') or '').strip()
    moved_from = str(payload.get('moved_from') or '').strip()
    moved_to = str(payload.get('moved_to') or '').strip()
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
    parsed_event = _parse_optional_date(payload.get('event_date', ''), 'event_date')
    if note_type == 'checked' and not headline and not detail:
        headline = 'Checked'
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
        raise ValueError(_validation_error_message(exc)) from exc
    note.save()
    note = AgentNote.objects.select_related('investor', 'author').get(pk=note.pk)
    return serialize_finding(note)


def _apply_finding_update(
    user: User,
    finding_id: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    note = (
        AgentNote.objects.select_related('investor', 'author')
        .filter(pk=finding_id)
        .first()
    )
    if note is None:
        raise ValueError(f'Finding {finding_id} not found.')
    if not can_edit_agent_note(user, note):
        raise PermissionError('You can only update findings you created.')

    if 'type' in payload and payload['type'] is not None:
        note.note_type = str(payload['type']).strip()
    if 'headline' in payload and payload['headline'] is not None:
        note.title = str(payload['headline']).strip()
    if 'detail' in payload and payload['detail'] is not None:
        note.body = str(payload['detail']).strip()
    if 'source_url' in payload and payload['source_url'] is not None:
        note.link = str(payload['source_url']).strip()
    if 'person' in payload and payload['person'] is not None:
        note.person_name = str(payload['person']).strip()
    if 'moved_from' in payload and payload['moved_from'] is not None:
        note.moved_from = str(payload['moved_from']).strip()
    if 'moved_to' in payload and payload['moved_to'] is not None:
        note.moved_to = str(payload['moved_to']).strip()
    if 'confidence' in payload and payload['confidence'] is not None:
        note.confidence = str(payload['confidence']).strip()

    clear_event_date = bool(payload.get('clear_event_date'))
    if clear_event_date or 'event_date' in payload:
        raw_date = payload.get('event_date', '')
        # Explicit clear flag, or any clear-token / blank / null value.
        if clear_event_date or _is_clear_date_value(raw_date):
            note.event_date = None
        else:
            note.event_date = _parse_optional_date(raw_date, 'event_date')

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
        raise ValueError(_validation_error_message(exc)) from exc
    note.save()
    note = AgentNote.objects.select_related('investor', 'author').get(pk=note.pk)
    return serialize_finding(note)


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
        return _create_finding_for_user(
            user,
            {
                'investor_id': investor_id,
                'type': type,
                'headline': headline,
                'source_url': source_url,
                'detail': detail,
                'event_date': event_date,
                'confidence': confidence,
                'person': person,
                'moved_from': moved_from,
                'moved_to': moved_to,
            },
        )
    finally:
        _close()


# Sentinel: omit event_date on update (MCP null/blank must still be able to clear).
EVENT_DATE_OMIT = '__omit__'


def update_finding(
    user_id: int | None,
    finding_id: int,
    *,
    type: str | None = None,
    headline: str | None = None,
    source_url: str | None = None,
    detail: str | None = None,
    event_date: Any = EVENT_DATE_OMIT,
    clear_event_date: bool = False,
    confidence: str | None = None,
    person: str | None = None,
    moved_from: str | None = None,
    moved_to: str | None = None,
) -> dict[str, Any]:
    _close()
    try:
        user = _require_agent(user_id)
        payload: dict[str, Any] = {}
        if type is not None:
            payload['type'] = type
        if headline is not None:
            payload['headline'] = headline
        if source_url is not None:
            payload['source_url'] = source_url
        if detail is not None:
            payload['detail'] = detail
        if confidence is not None:
            payload['confidence'] = confidence
        if person is not None:
            payload['person'] = person
        if moved_from is not None:
            payload['moved_from'] = moved_from
        if moved_to is not None:
            payload['moved_to'] = moved_to
        # Omitted → leave unchanged. null / "" / "null" / clear_event_date → clear.
        if clear_event_date or event_date is not EVENT_DATE_OMIT:
            payload['event_date'] = event_date
            payload['clear_event_date'] = clear_event_date
        return _apply_finding_update(user, finding_id, payload)
    finally:
        _close()


def bulk_add_findings(
    user_id: int | None,
    findings: list[dict[str, Any]],
) -> dict[str, Any]:
    """Create many findings in one call. Each item matches add_finding fields."""
    _close()
    try:
        user = _require_agent(user_id)
        if not isinstance(findings, list):
            raise ValueError('findings must be a list of objects.')
        if len(findings) > MAX_BULK_FINDINGS:
            raise ValueError(
                f'At most {MAX_BULK_FINDINGS} findings per bulk_add_findings call.'
            )
        created: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        for index, item in enumerate(findings):
            if not isinstance(item, dict):
                errors.append({'index': index, 'error': 'Item must be an object.'})
                continue
            try:
                created.append(_create_finding_for_user(user, item))
            except (ValueError, PermissionError) as exc:
                errors.append({'index': index, 'error': str(exc), 'input': item})
        return {
            'created_count': len(created),
            'error_count': len(errors),
            'created': created,
            'errors': errors,
        }
    finally:
        _close()


def bulk_update_findings(
    user_id: int | None,
    updates: list[dict[str, Any]],
) -> dict[str, Any]:
    """Update many findings in one call. Each item needs finding_id plus fields to change."""
    _close()
    try:
        user = _require_agent(user_id)
        if not isinstance(updates, list):
            raise ValueError('updates must be a list of objects.')
        if len(updates) > MAX_BULK_FINDINGS:
            raise ValueError(
                f'At most {MAX_BULK_FINDINGS} updates per bulk_update_findings call.'
            )
        updated: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        for index, item in enumerate(updates):
            if not isinstance(item, dict):
                errors.append({'index': index, 'error': 'Item must be an object.'})
                continue
            raw_id = item.get('finding_id', item.get('id'))
            try:
                finding_id = int(raw_id)
            except (TypeError, ValueError):
                errors.append(
                    {
                        'index': index,
                        'error': 'finding_id is required and must be an integer.',
                        'input': item,
                    }
                )
                continue
            payload = {k: v for k, v in item.items() if k not in ('finding_id', 'id')}
            try:
                updated.append(_apply_finding_update(user, finding_id, payload))
            except (ValueError, PermissionError) as exc:
                errors.append(
                    {
                        'index': index,
                        'finding_id': finding_id,
                        'error': str(exc),
                        'input': item,
                    }
                )
        return {
            'updated_count': len(updated),
            'error_count': len(errors),
            'updated': updated,
            'errors': errors,
        }
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
